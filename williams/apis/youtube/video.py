"""
YoutubeVideo  –  Represents a single YouTube video.

Metadata is fetched lazily on first property access and cached in-process.

Performance note
----------------
When a video comes from a playlist, the playlist response already contains
title, duration, and channel name.  ``YoutubePlaylist.iter_videos()`` seeds
these fields via ``_seed()`` so the common case (iterating titles) requires
*zero* additional HTTP calls.  A full fetch is only triggered when the caller
accesses a field not available in the playlist stub (e.g. description,
view_count, upload_date).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional, Union

import yt_dlp

from ._internal import _innertube as _yt
from ._internal._auth import YoutubeSession
from .creator import YoutubeCreator
from .exceptions import DownloadError, MediaError

TimestampInput = Union[float, int, str]


@dataclass(frozen=True)
class MediaFormat:
    """A single downloadable stream format from YouTube."""

    format_id: str
    ext: str
    resolution: Optional[str]
    width: Optional[int]
    height: Optional[int]
    fps: Optional[float]
    vcodec: Optional[str]
    acodec: Optional[str]
    filesize: Optional[int]
    tbr: Optional[float]
    format_note: str
    has_video: bool
    has_audio: bool
    is_dash: bool = False

    @property
    def label(self) -> str:
        parts = [self.format_id, self.ext]
        if self.resolution:
            parts.append(self.resolution)
        if self.fps:
            parts.append(f"{self.fps:g}fps")
        if self.vcodec:
            parts.append(self.vcodec.split(".")[0])
        if self.acodec and not self.has_video:
            parts.append(self.acodec.split(".")[0])
        if self.tbr:
            parts.append(f"{self.tbr:g}kbps")
        if self.format_note:
            parts.append(self.format_note)
        return " · ".join(parts)


@dataclass(frozen=True)
class DownloadResult:
    """Outcome of a completed download."""

    path: Path
    video_id: str
    title: str
    format_id: str
    ext: str
    filesize: Optional[int]


@dataclass(frozen=True)
class SubtitleTrack:
    """An available or downloaded subtitle track."""

    language: str
    language_code: str
    is_auto: bool
    ext: str
    path: Optional[Path] = None


def _require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise MediaError(
            "ffmpeg is required for frame extraction. "
            "Install ffmpeg and ensure it is on PATH."
        )
    return path


def parse_timestamp(value: TimestampInput) -> float:
    """
    Parse a timestamp into seconds.

    Accepts a float/int (seconds) or a string like ``"1:23"`` / ``"1:02:03"``.
    """
    if isinstance(value, (int, float)):
        if value < 0:
            raise ValueError("Timestamp must be non-negative")
        return float(value)

    text = str(value).strip()
    if not text:
        raise ValueError("Timestamp cannot be empty")

    if re.fullmatch(r"\d+(\.\d+)?", text):
        return float(text)

    parts = text.split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError as e:
        raise ValueError(f"Invalid timestamp: {value!r}") from e

    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    raise ValueError(f"Invalid timestamp: {value!r}")


def _format_selector(
    *,
    format_id: Optional[str] = None,
    quality: str = "best",
    video_only: bool = False,
    audio_only: bool = False,
) -> str:
    if format_id:
        return format_id

    q = quality.lower().strip()
    if audio_only:
        if q in ("best", "highest"):
            return "bestaudio/best"
        if q in ("worst", "lowest"):
            return "worstaudio/worst"
        return f"bestaudio[abr<={q}]/bestaudio/best"

    if video_only:
        if q in ("best", "highest"):
            return "bestvideo/best"
        if q in ("worst", "lowest"):
            return "worstvideo/worst"
        m = re.match(r"(\d+)p", q)
        if m:
            h = int(m.group(1))
            return f"bestvideo[height<={h}]/bestvideo/best"
        return "bestvideo/best"

    if q in ("best", "highest"):
        return "bestvideo+bestaudio/best"
    if q in ("worst", "lowest"):
        return "worstvideo+worstaudio/worst"
    m = re.match(r"(\d+)p", q)
    if m:
        h = int(m.group(1))
        return f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
    return "bestvideo+bestaudio/best"


@contextmanager
def _cookie_file(session: Optional[YoutubeSession]) -> Iterator[Optional[str]]:
    if session is None or not session.cookies:
        yield None
        return

    lines = ["# Netscape HTTP Cookie File", ""]
    for name, value in session.cookies.items():
        lines.append(f".youtube.com\tTRUE\t/\tTRUE\t0\t{name}\t{value}")

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8",
    )
    try:
        tmp.write("\n".join(lines))
        tmp.close()
        yield tmp.name
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def _parse_format_entry(entry: dict) -> MediaFormat:
    width = entry.get("width")
    height = entry.get("height")
    resolution = entry.get("resolution") or (
        f"{width}x{height}" if width and height else None
    )
    vcodec = entry.get("vcodec")
    acodec = entry.get("acodec")
    return MediaFormat(
        format_id=str(entry.get("format_id", "")),
        ext=entry.get("ext") or "",
        resolution=resolution if resolution and resolution != "audio only" else None,
        width=width,
        height=height,
        fps=entry.get("fps") or None,
        vcodec=None if vcodec in (None, "none") else vcodec,
        acodec=None if acodec in (None, "none") else acodec,
        filesize=entry.get("filesize") or entry.get("filesize_approx"),
        tbr=entry.get("tbr"),
        format_note=entry.get("format_note") or "",
        has_video=bool(vcodec and vcodec != "none"),
        has_audio=bool(acodec and acodec != "none"),
        is_dash=bool(entry.get("is_dash")),
    )


def extract_info(
    url: str,
    *,
    session: Optional[YoutubeSession] = None,
    download: bool = False,
) -> dict:
    opts = {"skip_download": not download, "quiet": True, "no_warnings": True}
    with _cookie_file(session) as cookiefile:
        if cookiefile:
            opts["cookiefile"] = cookiefile
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=download)


def list_formats(
    url: str,
    *,
    session: Optional[YoutubeSession] = None,
    video_only: bool = False,
    audio_only: bool = False,
) -> list[MediaFormat]:
    """Return all available formats for a video URL."""
    info = extract_info(url, session=session)
    formats: list[MediaFormat] = []
    for entry in info.get("formats") or []:
        fmt = _parse_format_entry(entry)
        if video_only and not fmt.has_video:
            continue
        if audio_only and not fmt.has_audio:
            continue
        if video_only and fmt.has_audio and not fmt.has_video:
            continue
        formats.append(fmt)
    return formats


def get_stream_url(
    url: str,
    *,
    session: Optional[YoutubeSession] = None,
    format_id: Optional[str] = None,
    quality: str = "best",
    video_only: bool = False,
    audio_only: bool = False,
) -> str:
    """Return a direct stream URL for the chosen format."""
    selector = _format_selector(
        format_id=format_id,
        quality=quality,
        video_only=video_only,
        audio_only=audio_only,
    )
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": selector,
        "skip_download": True,
    }
    with _cookie_file(session) as cookiefile:
        if cookiefile:
            opts["cookiefile"] = cookiefile
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                raise DownloadError(f"Could not extract stream info for {url!r}")
            if "url" in info:
                return info["url"]
            if "requestedFormats" in info:
                # Prefer a combined video stream for frame extraction.
                for part in info["requestedFormats"]:
                    if part.get("vcodec") not in (None, "none") and part.get("url"):
                        return part["url"]
                return info["requestedFormats"][0]["url"]
            raise DownloadError("No stream URL found in yt-dlp response")


def download(
    url: str,
    output: Union[str, Path] = ".",
    *,
    session: Optional[YoutubeSession] = None,
    format_id: Optional[str] = None,
    quality: str = "best",
    merge: bool = True,
    video_only: bool = False,
    audio_only: bool = False,
    progress: bool = False,
    filename: Optional[str] = None,
) -> DownloadResult:
    """
    Download a video (or audio) to *output*.

    Parameters
    ----------
    output : path
        Directory or full output file path.
    format_id : str | None
        Exact yt-dlp format id (from :func:`list_formats`).
    quality : str
        ``"best"``, ``"worst"``, ``"1080p"``, etc. Ignored when *format_id* set.
    merge : bool
        Merge separate video/audio streams into one file (mp4 by default).
    """
    output_path = Path(output)
    selector = _format_selector(
        format_id=format_id,
        quality=quality,
        video_only=video_only,
        audio_only=audio_only,
    )

    if filename:
        outtmpl = str(output_path / filename) if output_path.is_dir() else str(output_path)
    elif output_path.suffix:
        outtmpl = str(output_path)
    else:
        outtmpl = str(output_path / "%(title)s [%(id)s].%(ext)s")

    opts: dict[str, Any] = {
        "format": selector,
        "outtmpl": outtmpl,
        "quiet": not progress,
        "no_warnings": not progress,
        "noprogress": not progress,
    }
    if merge and not audio_only:
        opts["merge_output_format"] = "mp4"

    with _cookie_file(session) as cookiefile:
        if cookiefile:
            opts["cookiefile"] = cookiefile
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise DownloadError(f"Download failed for {url!r}")
                filepath = Path(ydl.prepare_filename(info))
        except DownloadError:
            raise
        except Exception as e:
            raise DownloadError(f"Download failed: {e}") from e

    if not filepath.exists() and merge:
        for ext in ("mp4", "mkv", "webm", info.get("ext", "mp4")):
            candidate = filepath.with_suffix(f".{ext}")
            if candidate.exists():
                filepath = candidate
                break

    if not filepath.exists():
        raise DownloadError(f"Expected output file not found: {filepath}")

    fmt_id = str(info.get("format_id") or format_id or selector)
    return DownloadResult(
        path=filepath,
        video_id=info.get("id") or "",
        title=info.get("title") or "",
        format_id=fmt_id,
        ext=filepath.suffix.lstrip("."),
        filesize=filepath.stat().st_size,
    )


def download_thumbnail(
    url: str,
    output: Optional[Path] = None,
    *,
    session: Optional[YoutubeSession] = None,
    quality: str = "max",
) -> Path:
    """Download the video thumbnail. Returns the saved file path."""
    info = extract_info(url, session=session)
    thumbs = info.get("thumbnails") or []
    if not thumbs:
        if thumb := info.get("thumbnail"):
            thumbs = [{"url": thumb}]
        else:
            raise DownloadError("No thumbnail available")

    if quality == "max":
        chosen = max(thumbs, key=lambda t: (t.get("width") or 0) * (t.get("height") or 0))
    else:
        try:
            idx = int(quality)
            chosen = thumbs[idx]
        except (ValueError, IndexError):
            chosen = thumbs[-1]

    thumb_url = chosen["url"]
    ext = "jpg"
    if ".png" in thumb_url:
        ext = "png"
    elif ".webp" in thumb_url:
        ext = "webp"

    if output is None:
        output = Path(tempfile.gettempdir()) / f"{info.get('id', 'thumb')}.{ext}"
    else:
        output = Path(output)
        if output.is_dir():
            output = output / f"{info.get('id', 'thumb')}.{ext}"

    r = _yt._scrape_http().get(thumb_url)
    r.raise_for_status()
    output.write_bytes(r.content)
    return output


def list_subtitles(
    url: str,
    *,
    session: Optional[YoutubeSession] = None,
) -> list[SubtitleTrack]:
    """Return available manual and automatic subtitle tracks."""
    info = extract_info(url, session=session)
    tracks: list[SubtitleTrack] = []

    for lang, subs in (info.get("subtitles") or {}).items():
        if not subs:
            continue
        ext = subs[0].get("ext", "vtt")
        tracks.append(SubtitleTrack(
            language=lang,
            language_code=lang,
            is_auto=False,
            ext=ext,
        ))

    for lang, subs in (info.get("automatic_captions") or {}).items():
        if not subs:
            continue
        ext = subs[0].get("ext", "vtt")
        tracks.append(SubtitleTrack(
            language=lang,
            language_code=lang,
            is_auto=True,
            ext=ext,
        ))

    return tracks


def download_subtitles(
    url: str,
    output: Union[str, Path] = ".",
    *,
    session: Optional[YoutubeSession] = None,
    languages: Optional[list[str]] = None,
    fmt: str = "srt",
    auto: bool = True,
) -> list[Path]:
    """Download subtitles for the given languages (defaults to English)."""
    output_path = Path(output)
    if output_path.suffix:
        out_dir = output_path.parent
        outtmpl = str(output_path.with_suffix(""))
    else:
        out_dir = output_path
        out_dir.mkdir(parents=True, exist_ok=True)
        info_probe = extract_info(url, session=session)
        outtmpl = str(out_dir / info_probe.get("id", "video"))

    langs = languages or ["en"]
    opts: dict[str, Any] = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": auto,
        "subtitleslangs": langs,
        "subtitlesformat": fmt,
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
    }
    with _cookie_file(session) as cookiefile:
        if cookiefile:
            opts["cookiefile"] = cookiefile
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            ydl.process_info(info)

    video_id = info.get("id") or Path(outtmpl).name
    found: list[Path] = []
    patterns = [
        f"{outtmpl}.{lang}.{fmt}" for lang in langs
    ] + [
        f"{outtmpl}.{lang}.auto.{fmt}" for lang in langs
    ]
    for pattern in patterns:
        p = Path(pattern)
        if p.exists():
            found.append(p)

    if not found:
        for path in out_dir.glob(f"{video_id}*.{fmt}"):
            found.append(path)
        for path in out_dir.glob(f"*{video_id}*.{fmt}"):
            if path not in found:
                found.append(path)

    if not found:
        raise DownloadError(f"No subtitles downloaded for languages: {langs}")
    return found


def extract_frame_at_timestamp(
    url: str,
    timestamp: TimestampInput,
    *,
    output: Optional[Path] = None,
    session: Optional[YoutubeSession] = None,
    format_id: Optional[str] = None,
    quality: str = "best",
    width: Optional[int] = None,
) -> Union[Path, bytes]:
    """
    Grab a single video frame at *timestamp* using ffmpeg.

    Returns a :class:`Path` when *output* is given, otherwise PNG bytes.
    """
    ffmpeg = _require_ffmpeg()
    seconds = parse_timestamp(timestamp)
    stream_url = get_stream_url(
        url,
        session=session,
        format_id=format_id,
        quality=quality,
        video_only=True,
    )

    if output is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        output = Path(tmp.name)
        delete_after = True
    else:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        delete_after = False

    cmd = [
        ffmpeg,
        "-ss", str(seconds),
        "-i", stream_url,
        "-frames:v", "1",
        "-f", "image2",
    ]
    if width:
        cmd.extend(["-vf", f"scale={width}:-1"])
    cmd.extend(["-y", str(output)])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as e:
        output.unlink(missing_ok=True)
        raise MediaError("ffmpeg timed out while extracting frame") from e

    if proc.returncode != 0:
        output.unlink(missing_ok=True)
        raise MediaError(
            f"ffmpeg failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )

    if delete_after:
        data = output.read_bytes()
        output.unlink(missing_ok=True)
        return data
    return output


class YoutubeVideo:
    """
    Represents a YouTube video.

    Parameters
    ----------
    url_or_id : str
        Full YouTube URL or an 11-character video ID.

    Examples
    --------
    >>> v = YoutubeVideo("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    >>> print(v.title, v.duration_formatted)
    >>> print(v.view_count)
    """

    # Fields populated from a playlist stub (no extra HTTP call needed)
    _STUB_FIELDS = frozenset(
        {"title", "duration_seconds", "duration_formatted", "channel_name",
         "channel_id", "thumbnail_url"}
    )

    def __init__(
        self,
        url_or_id: str,
        session: Optional[YoutubeSession] = None,
    ) -> None:
        self._video_id = _yt.extract_video_id(url_or_id)
        self._session = session
        self._lock = threading.Lock()

        # _stub: partial data seeded from a playlist response (no HTTP call)
        # _data: full data from a dedicated /player fetch
        self._stub: Optional[dict] = None
        self._data: Optional[dict] = None

    # ------------------------------------------------------------------
    # Internal: data seeding & loading
    # ------------------------------------------------------------------

    def _seed(self, stub: dict) -> None:
        """
        Pre-populate fields from a playlist stub.  Called by YoutubePlaylist
        *before* returning the video; no lock needed since the object isn't
        shared yet.
        """
        self._stub = stub

    def _ensure_full_data(self) -> dict:
        """Return full data, fetching if necessary (thread-safe)."""
        if self._data is not None:
            return self._data

        with self._lock:
            if self._data is not None:
                return self._data
            self._data = _yt.fetch_video_data(self._video_id)
        return self._data

    def _get(self, field: str):
        """
        Return a field value, using the stub if available and sufficient,
        otherwise triggering a full fetch.
        """
        # Stub covers this field?
        if self._stub is not None and field in self._STUB_FIELDS:
            return self._stub.get(field)
        # Full fetch required
        return self._ensure_full_data().get(field)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def video_id(self) -> str:
        return self._video_id

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self._video_id}"

    @property
    def short_url(self) -> str:
        return f"https://youtu.be/{self._video_id}"

    def __repr__(self) -> str:
        # Get title from stub or data, or fetch if needed
        if self._stub is not None:
            title = self._stub.get("title")
        elif self._data is not None:
            title = self._data.get("title")
        else:
            # Fetch the data to get the title
            try:
                self._ensure_full_data()
                title = self._data.get("title") if self._data else None
            except Exception:
                title = None
        if not title:
            title = "?"
        return f"YoutubeVideo(id={self._video_id!r}, title={title!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, YoutubeVideo):
            return self._video_id == other._video_id
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._video_id)

    # ------------------------------------------------------------------
    # Metadata — cheap (available from playlist stub)
    # ------------------------------------------------------------------

    @property
    def title(self) -> str:
        """Video title."""
        return self._get("title") or ""

    @property
    def duration_seconds(self) -> int:
        """Duration in seconds."""
        return self._get("duration_seconds") or 0

    @property
    def duration_formatted(self) -> str:
        """Duration as 'H:MM:SS' or 'M:SS'."""
        return self._get("duration_formatted") or ""

    @property
    def channel_name(self) -> str:
        """Name of the uploading channel."""
        return self._get("channel_name") or ""

    @property
    def channel_id(self) -> str:
        """Channel ID (UC…)."""
        return self._get("channel_id") or ""

    @property
    def thumbnail_url(self) -> str:
        """URL of the video thumbnail."""
        return self._get("thumbnail_url") or ""

    # ------------------------------------------------------------------
    # Metadata — requires full fetch
    # ------------------------------------------------------------------

    @property
    def description(self) -> str:
        """Full video description."""
        return self._ensure_full_data().get("description") or ""

    @property
    def view_count(self) -> int:
        """Total view count."""
        return self._ensure_full_data().get("view_count") or 0

    @property
    def like_count(self) -> int:
        """Like count (may be 0 if hidden by creator)."""
        return self._ensure_full_data().get("like_count") or 0

    @property
    def upload_date(self) -> str:
        """Upload date as ISO-8601 string (e.g. '2024-01-15')."""
        return self._ensure_full_data().get("upload_date") or ""

    @property
    def is_live(self) -> bool:
        """True if this is a live stream."""
        return bool(self._ensure_full_data().get("is_live"))

    @property
    def keywords(self) -> list[str]:
        """List of video tags / keywords."""
        return self._ensure_full_data().get("keywords") or []

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def get_metadata(self) -> dict:
        """Return all metadata as a plain dict (triggers full fetch)."""
        data = self._ensure_full_data()
        return {
            "video_id":          self._video_id,
            "url":               self.url,
            "title":             data.get("title", ""),
            "description":       data.get("description", ""),
            "duration_seconds":  data.get("duration_seconds", 0),
            "duration_formatted": data.get("duration_formatted", ""),
            "view_count":        data.get("view_count", 0),
            "like_count":        data.get("like_count", 0),
            "upload_date":       data.get("upload_date", ""),
            "channel_name":      data.get("channel_name", ""),
            "channel_id":        data.get("channel_id", ""),
            "thumbnail_url":     data.get("thumbnail_url", ""),
            "is_live":           data.get("is_live", False),
            "keywords":          data.get("keywords", []),
        }

    def prefetch(self) -> YoutubeVideo:
        """Eagerly fetch all metadata. Returns self for chaining."""
        self._ensure_full_data()
        return self

    def reload(self) -> YoutubeVideo:
        """Bust the cache and re-fetch. Returns self."""
        with self._lock:
            self._data = None
            self._stub = None
        return self

    def get_creator(self) -> YoutubeCreator:
        """Return a :class:`YoutubeCreator` for this video's channel."""
        cid = self.channel_id
        if cid:
            return YoutubeCreator(cid)
        return YoutubeCreator(self.channel_name)

    # ------------------------------------------------------------------
    # Media — download, streams, frames, subtitles
    # ------------------------------------------------------------------

    @property
    def session(self) -> Optional[YoutubeSession]:
        """Authenticated session used for age-restricted / private downloads."""
        return self._session

    def list_formats(
        self,
        *,
        video_only: bool = False,
        audio_only: bool = False,
    ) -> list[MediaFormat]:
        """
        List all downloadable formats (video, audio, combined).

        Uses yt-dlp under the hood — requires ``pip install yt-dlp``.
        """
        return list_formats(
            self.url,
            session=self._session,
            video_only=video_only,
            audio_only=audio_only,
        )

    def get_format(self, format_id: str) -> MediaFormat:
        """Return a single format by id (raises :class:`MediaError` if missing)."""
        for fmt in self.list_formats():
            if fmt.format_id == format_id:
                return fmt
        raise MediaError(f"Format {format_id!r} not found for {self.video_id}")

    def get_stream_url(
        self,
        *,
        format_id: Optional[str] = None,
        quality: str = "best",
        video_only: bool = False,
        audio_only: bool = False,
    ) -> str:
        """Return a direct stream URL for the selected format."""
        return get_stream_url(
            self.url,
            session=self._session,
            format_id=format_id,
            quality=quality,
            video_only=video_only,
            audio_only=audio_only,
        )

    def download(
        self,
        output: Union[str, Path] = ".",
        *,
        format_id: Optional[str] = None,
        quality: str = "best",
        merge: bool = True,
        video_only: bool = False,
        audio_only: bool = False,
        progress: bool = False,
        filename: Optional[str] = None,
        session: Optional[YoutubeSession] = None,
    ) -> DownloadResult:
        """
        Download this video to *output*.

        Parameters
        ----------
        output : path
            Output directory or full file path.
        format_id : str | None
            Exact format id from :meth:`list_formats`.
        quality : str
            ``"best"``, ``"worst"``, ``"1080p"``, etc.
        merge : bool
            Merge separate video/audio into mp4 (default True).
        video_only / audio_only : bool
            Download only one stream type.
        progress : bool
            Show yt-dlp progress bar.

        Returns
        -------
        DownloadResult
        """
        return download(
            self.url,
            output,
            session=session or self._session,
            format_id=format_id,
            quality=quality,
            merge=merge,
            video_only=video_only,
            audio_only=audio_only,
            progress=progress,
            filename=filename,
        )

    def download_audio(
        self,
        output: Union[str, Path] = ".",
        *,
        quality: str = "best",
        progress: bool = False,
        session: Optional[YoutubeSession] = None,
    ) -> DownloadResult:
        """Download audio only (mp3/m4a/webm depending on format)."""
        return self.download(
            output,
            quality=quality,
            audio_only=True,
            merge=False,
            progress=progress,
            session=session,
        )

    def download_thumbnail(
        self,
        output: Optional[Path] = None,
        *,
        quality: str = "max",
    ) -> Path:
        """Download the video thumbnail image."""
        return download_thumbnail(
            self.url, output, session=self._session, quality=quality,
        )

    def list_subtitles(self) -> list[SubtitleTrack]:
        """Return available manual and automatic subtitle tracks."""
        return list_subtitles(self.url, session=self._session)

    def download_subtitles(
        self,
        output: Union[str, Path] = ".",
        *,
        languages: Optional[list[str]] = None,
        fmt: str = "srt",
        auto: bool = True,
        session: Optional[YoutubeSession] = None,
    ) -> list[Path]:
        """Download subtitles for the given languages (default: English)."""
        return download_subtitles(
            self.url,
            output,
            session=session or self._session,
            languages=languages,
            fmt=fmt,
            auto=auto,
        )

    def get_frame_at_timestamp(
        self,
        timestamp: Union[float, int, str],
        *,
        output: Optional[Path] = None,
        format_id: Optional[str] = None,
        quality: str = "best",
        width: Optional[int] = None,
        session: Optional[YoutubeSession] = None,
    ) -> Union[Path, bytes]:
        """
        Extract a single frame at *timestamp* using ffmpeg.

        Parameters
        ----------
        timestamp : float | str
            Seconds (``45.5``) or ``"M:SS"`` / ``"H:MM:SS"`` string.
        output : Path | None
            Save to this path; returns PNG bytes if omitted.
        width : int | None
            Optionally scale the frame to this width (height auto).

        Returns
        -------
        Path | bytes
        """
        return extract_frame_at_timestamp(
            self.url,
            timestamp,
            output=output,
            session=session or self._session,
            format_id=format_id,
            quality=quality,
            width=width,
        )

    @staticmethod
    def parse_timestamp(value: Union[float, int, str]) -> float:
        """Parse ``"1:23"`` / ``"1:02:03"`` / seconds into a float."""
        return parse_timestamp(value)