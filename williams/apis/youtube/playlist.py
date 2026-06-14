"""
YoutubePlaylist  –  Represents a YouTube playlist.

Performance design
------------------
The InnerTube ``/browse?browseId=VL<id>`` endpoint returns title, duration,
channel name, and thumbnail for *every* video in the playlist in a single
HTTP request (plus continuation pages for lists > ~100 videos).

``iter_videos()`` seeds each ``YoutubeVideo`` with that stub data, so
accessing ``.title`` or ``.duration_formatted`` on the returned objects
requires **no additional HTTP calls**.  Full metadata (description,
view_count, etc.) is only fetched if explicitly requested.
"""

from __future__ import annotations

import concurrent.futures
import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import Iterator, Optional

from ._internal import _innertube
from ._internal._auth import YoutubeSession
from .creator import YoutubeCreator
from .exceptions import PlaylistNotFoundError
from .video import YoutubeVideo


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class PlaylistInfo:
    """Snapshot of playlist metadata."""
    playlist_id:   str
    title:         str
    description:   str
    video_count:   int
    owner:         str
    owner_id:      str
    visibility:    str          # "public" (private raises before we get here)
    last_updated:  Optional[str]
    thumbnail_url: Optional[str]


# ---------------------------------------------------------------------------
# YoutubePlaylist
# ---------------------------------------------------------------------------

class YoutubePlaylist:
    """
    Represents a YouTube playlist.

    Metadata and video list are fetched lazily on first access and cached.

    Parameters
    ----------
    url_or_id : str
        Full playlist URL or a bare playlist ID (``PL…``, ``RD…``, etc.).

    Examples
    --------
    >>> pl = YoutubePlaylist("PLrEnWoR732...")
    >>> print(pl.title, pl.video_count)
    >>> for video in pl.iter_videos():       # fast – no per-video HTTP call
    ...     print(video.title, video.duration_formatted)
    >>> videos = pl.get_videos()             # returns a list
    """

    def __init__(
        self,
        url_or_id: str,
        session: Optional[YoutubeSession] = None,
    ) -> None:
        self._playlist_id = _innertube.extract_playlist_id(url_or_id)
        self._url = f"https://www.youtube.com/playlist?list={self._playlist_id}"
        self._session = session
        self._lock = threading.Lock()
        self._data: Optional[dict] = None   # populated by _ensure_data()

    # ------------------------------------------------------------------
    # Internal loading
    # ------------------------------------------------------------------

    def _ensure_data(self, max_videos: int = 0) -> None:
        """Fetch and cache playlist data if not already loaded."""
        if self._data is not None:
            return
        
        with self._lock:
            if self._data is not None:
                return
            data = _innertube.fetch_playlist_data(
                self._playlist_id,
                max_videos=max_videos,
                session=self._session,
            )
            self._data = data

    def _d(self) -> dict:
        """Return the loaded data dict (ensures it's been fetched)."""
        self._ensure_data()
        assert self._data is not None
        return self._data

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def playlist_id(self) -> str:
        return self._playlist_id

    @property
    def url(self) -> str:
        return self._url

    def __repr__(self) -> str:
        # Ensure data is loaded before accessing it
        try:
            self._ensure_data()
            title = self._data.get("title", "?") if self._data else "?"
        except Exception:
            title = "?"
        return f"YoutubePlaylist(id={self._playlist_id!r}, title={title!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, YoutubePlaylist):
            return self._playlist_id == other._playlist_id
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._playlist_id)

    def __len__(self) -> int:
        return self.video_count

    def __iter__(self) -> Iterator[YoutubeVideo]:
        return self.iter_videos()

    # ------------------------------------------------------------------
    # Metadata properties
    # ------------------------------------------------------------------

    @property
    def title(self) -> str:
        return self._d().get("title", "")

    @property
    def description(self) -> str:
        return self._d().get("description", "")

    @property
    def video_count(self) -> int:
        return self._d().get("video_count", 0)

    @property
    def owner(self) -> str:
        return self._d().get("owner", "")

    @property
    def owner_id(self) -> str:
        return self._d().get("owner_id", "")

    @property
    def owner_handle(self) -> Optional[str]:
        """
        The handle of the playlist owner (e.g., ``@Redlist-JustHits``).
        
        Returns
        -------
        str | None
            The owner's handle, or None if not available.
        """
        return self._d().get("owner_handle")

    @property
    def thumbnail_url(self) -> Optional[str]:
        return self._d().get("thumbnail_url")

    @property
    def last_updated(self) -> Optional[str]:
        return self._d().get("last_updated")

    @property
    def views(self) -> int:
        """
        Total number of views for this playlist.
        
        Returns
        -------
        int
            The total view count, or 0 if not available.
        """
        return self._d().get("views", 0)

    def get_playlist_views(self) -> int:
        """
        Return the total number of views for this playlist.
        
        This is an alias for the ``views`` property provided for explicit
        method-call style.
        
        Returns
        -------
        int
            The total view count, or 0 if not available.
        
        Examples
        --------
        >>> pl = YoutubePlaylist("PLrEnWoR732...")
        >>> print(pl.get_playlist_views())
        1234567
        """
        return self.views

    def get_info(self) -> PlaylistInfo:
        """Return a :class:`PlaylistInfo` snapshot of all metadata."""
        return PlaylistInfo(
            playlist_id  = self._playlist_id,
            title        = self.title,
            description  = self.description,
            video_count  = self.video_count,
            owner        = self.owner,
            owner_id     = self.owner_id,
            visibility   = "public",
            last_updated = self.last_updated,
            thumbnail_url= self.thumbnail_url,
        )

    def get_metadata(self) -> dict:
        """Return playlist metadata as a plain dict."""
        return {
            "playlist_id":  self._playlist_id,
            "url":          self._url,
            "title":        self.title,
            "description":  self.description,
            "video_count":  self.video_count,
            "owner":        self.owner,
            "owner_id":     self.owner_id,
            "thumbnail_url": self.thumbnail_url,
            "last_updated": self.last_updated,
            "views":        self.views,
        }

    def get_video_count(self) -> int:
        """
        Return the number of videos in this playlist.
        
        This is an alias for the ``video_count`` property provided for explicit
        method-call style.
        
        Returns
        -------
        int
            The number of videos in the playlist.
        """
        return self.video_count

    def get_owner(self) -> str:
        """
        Return the owner name of this playlist.
        
        This is an alias for the ``owner`` property provided for explicit
        method-call style.
        
        Returns
        -------
        str
            The owner name.
        """
        return self.owner

    def get_owner_id(self) -> str:
        """
        Return the owner ID of this playlist.
        
        This is an alias for the ``owner_id`` property provided for explicit
        method-call style.
        
        Returns
        -------
        str
            The owner channel ID.
        """
        return self.owner_id

    # ------------------------------------------------------------------
    # Video retrieval  ←  core feature / performance-critical
    # ------------------------------------------------------------------

    def _make_video(self, stub: dict) -> YoutubeVideo:
        """Create a YoutubeVideo pre-seeded with stub data from the playlist."""
        v = YoutubeVideo(stub["video_id"])
        v._seed(stub)
        return v

    def iter_videos(
        self,
        max_videos: int = 0,
    ) -> Iterator[YoutubeVideo]:
        """
        Iterate over videos in this playlist.

        Each yielded :class:`YoutubeVideo` is pre-seeded with title,
        duration, and channel from the playlist response — **no per-video
        HTTP call is made** unless you access a field not in the playlist
        data (description, view_count, upload_date).

        Parameters
        ----------
        max_videos : int
            Stop after this many videos (0 = all).

        Yields
        ------
        YoutubeVideo
        """
        self._ensure_data(max_videos=max_videos)
        stubs = self._data["videos"]  # type: ignore[index]
        if max_videos:
            stubs = stubs[:max_videos]
        for stub in stubs:
            yield self._make_video(stub)

    def get_videos(
        self,
        max_videos: int = 0,
        prefetch_metadata: bool = False,
        workers: int = 8,
    ) -> list[YoutubeVideo]:
        """
        Return all videos as a list.

        Parameters
        ----------
        max_videos : int
            Maximum videos to return (0 = all).
        prefetch_metadata : bool
            If True, eagerly fetch *full* metadata (description, view_count,
            etc.) for every video in parallel before returning.  Only needed
            if you'll access those deeper fields.
        workers : int
            Thread-pool size for ``prefetch_metadata=True``.

        Returns
        -------
        list[YoutubeVideo]
        """
        videos = list(self.iter_videos(max_videos=max_videos))

        if prefetch_metadata and videos:
            def _prefetch(v: YoutubeVideo) -> YoutubeVideo:
                try:
                    v._ensure_full_data()
                except Exception:
                    pass
                return v

            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                videos = list(ex.map(_prefetch, videos))

        return videos

    def get_video_ids(self, max_videos: int = 0) -> list[str]:
        """Return just the video IDs (no YoutubeVideo objects created)."""
        self._ensure_data(max_videos=max_videos)
        stubs = self._data["videos"]  # type: ignore[index]
        if max_videos:
            stubs = stubs[:max_videos]
        return [s["video_id"] for s in stubs]

    def get_video_at_index(self, index: int) -> YoutubeVideo:
        """
        Return the video at position *index* (0-based).

        Raises
        ------
        IndexError
        """
        self._ensure_data()
        stubs = self._data["videos"]  # type: ignore[index]
        if index < 0 or index >= len(stubs):
            raise IndexError(
                f"Index {index} out of range for playlist of length {len(stubs)}."
            )
        return self._make_video(stubs[index])

    # ------------------------------------------------------------------
    # Aggregate / computed
    # ------------------------------------------------------------------

    def total_duration(self) -> int:
        """
        Sum of all video durations in seconds.

        Uses stub duration data from the playlist response — **no extra
        HTTP calls** needed.
        """
        self._ensure_data()
        return sum(s.get("duration_seconds", 0) for s in self._data["videos"])  # type: ignore[index]

    def total_duration_formatted(self) -> str:
        """Human-readable total duration, e.g. ``'4:32:10'``."""
        secs = self.total_duration()
        h, r = divmod(secs, 3600)
        m, s = divmod(r, 60)
        return f"{h}:{m:02d}:{s:02d}"

    def filter_videos(
        self,
        min_duration: Optional[int] = None,
        max_duration: Optional[int] = None,
        title_contains: Optional[str] = None,
    ) -> list[YoutubeVideo]:
        """
        Filter videos by duration and/or title substring.

        Uses stub data — **no per-video HTTP calls** for duration/title
        filtering.

        Parameters
        ----------
        min_duration : int | None
            Minimum duration in seconds.
        max_duration : int | None
            Maximum duration in seconds.
        title_contains : str | None
            Case-insensitive substring match on title.

        Returns
        -------
        list[YoutubeVideo]
        """
        needle = title_contains.lower() if title_contains else None
        results: list[YoutubeVideo] = []
        for v in self.iter_videos():
            dur = v.duration_seconds
            if min_duration is not None and dur < min_duration:
                continue
            if max_duration is not None and dur > max_duration:
                continue
            if needle and needle not in v.title.lower():
                continue
            results.append(v)
        return results

    def get_owner_creator(self) -> YoutubeCreator:
        """Return a :class:`YoutubeCreator` for this playlist's owner."""
        oid = self.owner_id
        if oid:
            return YoutubeCreator(oid)
        return YoutubeCreator(f"@{self.owner}")

    def reload(self) -> "YoutubePlaylist":
        """Bust the cache and re-fetch all data. Returns self."""
        with self._lock:
            self._data = None
        return self

    # ------------------------------------------------------------------
    # Authenticated mutations  (requires YoutubeSession with cookies)
    # ------------------------------------------------------------------

    @property
    def session(self) -> Optional[YoutubeSession]:
        """The authenticated session used for write operations, if any."""
        return self._session

    def add_video(
        self,
        video: "str | YoutubeVideo",
        *,
        session: Optional[YoutubeSession] = None,
    ) -> dict:
        """
        Add a video to this playlist.

        Requires browser cookies from a logged-in YouTube account::

            from lib import YoutubeSession, YoutubePlaylist

            session = YoutubeSession.from_cookies("cookies.txt")
            pl = YoutubePlaylist("PLxxx", session=session)
            pl.add_video("dQw4w9WgXcQ")

        Parameters
        ----------
        video : str | YoutubeVideo
            Video URL, ID, or :class:`YoutubeVideo` instance.
        session : YoutubeSession | None
            Override the session attached to this playlist.

        Returns
        -------
        dict
            Raw InnerTube API response.
        """
        vid = video.video_id if isinstance(video, YoutubeVideo) else video
        result = _innertube.add_video_to_playlist(
            self._playlist_id, vid, session=session or self._session,
        )
        self.reload()
        return result

    def remove_video(
        self,
        video: "str | YoutubeVideo",
        *,
        session: Optional[YoutubeSession] = None,
    ) -> dict:
        """
        Remove a video from this playlist. Requires authentication.

        See :meth:`add_video` for cookie setup.
        """
        vid = video.video_id if isinstance(video, YoutubeVideo) else video
        result = _innertube.remove_video_from_playlist(
            self._playlist_id, vid, session=session or self._session,
        )
        self.reload()
        return result