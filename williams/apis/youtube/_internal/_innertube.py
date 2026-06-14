"""
_innertube.py - Low-level YouTube data client.

Strategy (in priority order)
------------------------------
Video metadata
  1. Scrape the watch page HTML (ytInitialPlayerResponse + ytInitialData).
     Most reliable; doesn't require API keys or PO tokens.
  2. InnerTube /player via android_vr client (no JS player, no PO token needed).
  3. InnerTube /player via tv_simply client.

Playlist metadata
  1. InnerTube /browse?browseId=VL<id>  (returns all stubs in one shot).
  2. Follow continuation tokens for playlists > ~100 videos.

Channel metadata
  1. InnerTube /browse?browseId=@handle or UC...

HTTP
  - Single persistent httpx.Client with connection pooling + HTTP/2.
  - All requests share one TCP connection pool (no per-call handshakes).
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any, Optional
import html as html_lib

import httpx

from ._auth import YoutubeSession
from williams.apis.youtube.exceptions import (
    ParseError, PlaylistNotFoundError, VideoNotFoundError, RateLimitError, AuthenticationError
)

# ---------------------------------------------------------------------------
# Shared HTTP client  (singleton, thread-safe)
# ---------------------------------------------------------------------------

_CLIENT_LOCK = threading.Lock()
_HTTP: Optional[httpx.Client] = None
_SCRAPE_HTTP: Optional[httpx.Client] = None

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Origin": "https://www.youtube.com",
    "Referer": "https://www.youtube.com/",
}

_CLIENT_NAME_IDS = {
    "WEB": "1",
    "WEB_EMBEDDED_PLAYER": "56",
    "ANDROID": "3",
    "ANDROID_VR": "28",
    "TVHTML5_SIMPLY": "85",
}


def _make_client() -> httpx.Client:
    return httpx.Client(
        http2=True,
        timeout=httpx.Timeout(20.0, connect=10.0),
        limits=httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10,
            keepalive_expiry=30,
        ),
        headers=_HEADERS,
        follow_redirects=True,
    )


def _http() -> httpx.Client:
    """Shared InnerTube API client (may carry auth cookies)."""
    global _HTTP
    if _HTTP is None:
        with _CLIENT_LOCK:
            if _HTTP is None:
                _HTTP = _make_client()
    return _HTTP


def _scrape_http() -> httpx.Client:
    """Isolated client for HTML scrapes — avoids polluting API cookies."""
    global _SCRAPE_HTTP
    if _SCRAPE_HTTP is None:
        with _CLIENT_LOCK:
            if _SCRAPE_HTTP is None:
                _SCRAPE_HTTP = _make_client()
    return _SCRAPE_HTTP


def _apply_session_cookies(session: Optional[YoutubeSession]) -> None:
    """Merge session cookies into the shared API client."""
    if session is None:
        return
    client = _http()
    for name, value in session.cookies.items():
        client.cookies.set(name, value, domain=".youtube.com")


# ---------------------------------------------------------------------------
# InnerTube client configurations
# Versions kept in sync with yt-dlp 2026.03 to stay current.
# ---------------------------------------------------------------------------

_INNERTUBE_BASE_URL = "https://www.youtube.com/youtubei/v1/{endpoint}"
_INNERTUBE_API_KEY  = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"

_CTX_ANDROID_VR = {
    "client": {
        "clientName": "ANDROID_VR",
        "clientVersion": "1.65.10",
        "deviceMake": "Oculus",
        "deviceModel": "Quest 3",
        "androidSdkVersion": 32,
        "userAgent": (
            "com.google.android.apps.youtube.vr.oculus/1.65.10 "
            "(Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip"
        ),
        "osName": "Android",
        "osVersion": "12L",
        "hl": "en",
        "gl": "US",
    }
}

_CTX_TV_SIMPLY = {
    "client": {
        "clientName": "TVHTML5_SIMPLY",
        "clientVersion": "1.0",
        "hl": "en",
        "gl": "US",
    }
}

_CTX_WEB = {
    "client": {
        "clientName": "WEB",
        "clientVersion": "2.20260114.08.00",
        "hl": "en",
        "gl": "US",
    }
}


# ---------------------------------------------------------------------------
# Visitor data
# ---------------------------------------------------------------------------

_VISITOR_DATA_LOCK = threading.Lock()
_VISITOR_DATA: Optional[str] = None
_VISITOR_DATA_RE = re.compile(r'"visitorData"\s*:\s*"([^"]+)"')


def _fetch_visitor_data() -> Optional[str]:
    try:
        html = _fetch_page("https://www.youtube.com/")
        m = _VISITOR_DATA_RE.search(html)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def _get_visitor_data() -> Optional[str]:
    global _VISITOR_DATA
    if _VISITOR_DATA is None:
        with _VISITOR_DATA_LOCK:
            if _VISITOR_DATA is None:
                _VISITOR_DATA = _fetch_visitor_data()
    return _VISITOR_DATA


# ---------------------------------------------------------------------------
# Core HTTP POST
# ---------------------------------------------------------------------------

def _innertube_post(
    endpoint: str,
    body: dict,
    context: dict = _CTX_WEB,
    session: Optional[YoutubeSession] = None,
    *,
    require_auth: bool = False,
) -> dict:
    """POST to an InnerTube endpoint and return the parsed JSON response."""
    if require_auth:
        if session is None:
            raise AuthenticationError(
                "This operation requires authentication. "
                "Use YoutubeSession.from_cookies('cookies.txt') or set_cookies()."
            )
        session.require_auth()

    url = _INNERTUBE_BASE_URL.format(endpoint=endpoint)
    payload = {"context": context, **body}

    client_name    = context.get("client", {}).get("clientName", "WEB")
    client_version = context.get("client", {}).get("clientVersion", "")
    visitor_data   = _get_visitor_data()

    extra_headers: dict[str, str] = {
        "Content-Type":             "application/json",
        "X-YouTube-Client-Name":    _CLIENT_NAME_IDS.get(client_name, "1"),
        "X-YouTube-Client-Version": client_version,
    }
    if visitor_data:
        extra_headers["X-Goog-Visitor-Id"] = visitor_data

    if session is not None:
        _apply_session_cookies(session)
        if session.is_authenticated:
            extra_headers["Authorization"] = session.authorization_header()
            extra_headers["X-Goog-AuthUser"] = "0"
            extra_headers["X-Origin"] = "https://www.youtube.com"
            # X-Goog-PageId is required for brand/secondary channel accounts.
            # Without it, YouTube returns 403 PERMISSION_DENIED on mutations
            # even though the cookies are valid.
            if session.delegated_session_id:
                extra_headers["X-Goog-PageId"] = session.delegated_session_id

    r = _http().post(
        url,
        json=payload,
        params={"key": _INNERTUBE_API_KEY, "prettyPrint": "false"},
        headers=extra_headers,
    )
    if r.status_code == 429:
        raise RateLimitError("YouTube is rate-limiting requests (429).")
    if r.status_code in (401, 403) and require_auth:
        raise AuthenticationError(
            f"YouTube rejected the authenticated request ({r.status_code}). "
            "Cookies may be expired — re-export from your browser."
        )
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# URL / ID parsing
# ---------------------------------------------------------------------------

_VIDEO_ID_RE = re.compile(
    r"(?:(?:v|vi|video_id)=|youtu\.be/|/(?:shorts|embed|v)/)([a-zA-Z0-9_-]{11})"
)
_PLAYLIST_ID_RE = re.compile(
    r"(?:list=|^)((?:PL|RD|UU|FL|OL)[a-zA-Z0-9_-]+)", re.IGNORECASE
)
_CHANNEL_RE = re.compile(
    r"youtube\.com/(?:@([^/?#\s]+)|channel/(UC[a-zA-Z0-9_-]+)|c/([^/?#\s]+)|user/([^/?#\s]+))"
)


def extract_video_id(url_or_id: str) -> str:
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", url_or_id):
        return url_or_id
    m = _VIDEO_ID_RE.search(url_or_id)
    if m:
        return m.group(1)
    raise ValueError(f"Cannot extract video ID from {url_or_id!r}")


def extract_playlist_id(url_or_id: str) -> str:
    if re.fullmatch(r"(?:PL|RD|UU|FL|OL)[a-zA-Z0-9_-]+", url_or_id, re.IGNORECASE):
        return url_or_id
    m = _PLAYLIST_ID_RE.search(url_or_id)
    if m:
        return m.group(1)
    raise ValueError(f"Cannot extract playlist ID from {url_or_id!r}")


def extract_channel_handle(url_or_id: str) -> str:
    m = _CHANNEL_RE.search(url_or_id)
    if m:
        handle, uc_id, c_name, user = m.groups()
        if handle:   return f"@{handle}"
        if uc_id:    return uc_id
        if c_name:   return c_name
        if user:     return user
    if url_or_id.startswith("UC") and len(url_or_id) > 10:
        return url_or_id
    if url_or_id.startswith("@"):
        return url_or_id
    if not url_or_id.startswith("http"):
        return f"@{url_or_id}"
    raise ValueError(f"Cannot extract channel identifier from {url_or_id!r}")


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _dig(obj: Any, *keys) -> Any:
    for k in keys:
        if obj is None:
            return None
        try:
            obj = obj[k]
        except (KeyError, IndexError, TypeError):
            return None
    return obj


def _runs_text(obj: Any) -> str:
    if obj is None:
        return ""
    runs = obj.get("runs") if isinstance(obj, dict) else []
    return "".join(r.get("text", "") for r in (runs or []))


def _simple_or_runs(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, dict):
        if "simpleText" in obj:
            return obj["simpleText"]
        return _runs_text(obj)
    return str(obj)


def _duration_to_seconds(text: str) -> int:
    if not text:
        return 0
    parts = text.strip().split(":")
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return 0
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] if parts else 0


def _format_duration(secs: int) -> str:
    h, r = divmod(secs, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# Webpage JSON extraction
# ---------------------------------------------------------------------------

def _extract_json_object(text: str, start: int) -> Optional[str]:
    depth = 0
    in_string = False
    escape_next = False
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if escape_next:
            escape_next = False
        elif c == "\\" and in_string:
            escape_next = True
        elif c == '"' and not escape_next:
            in_string = not in_string
        elif not in_string:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    return None


def _extract_yt_var(html: str, var_name: str) -> Optional[dict]:
    pattern = re.compile(
        r'(?:var\s+|window\[")' + re.escape(var_name) + r'(?:"\])?\s*=\s*(\{)',
        re.DOTALL,
    )
    m = pattern.search(html)
    if not m:
        return None
    raw = _extract_json_object(html, m.start(1))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _fetch_page(url: str) -> str:
    r = _scrape_http().get(
        url,
        headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    if r.status_code == 429:
        raise RateLimitError("YouTube is rate-limiting requests (429).")
    r.raise_for_status()
    return r.text


# ---------------------------------------------------------------------------
# Video data fetching
# ---------------------------------------------------------------------------

def _parse_player_response(pr: dict, video_id: str) -> dict:
    vd  = pr.get("videoDetails") or {}
    ms  = _dig(pr, "microformat", "playerMicroformatRenderer") or {}

    title        = vd.get("title", "") or ms.get("title", {}).get("simpleText", "")
    description  = vd.get("shortDescription", "") or _simple_or_runs(ms.get("description"))
    channel_name = vd.get("author", "") or ms.get("ownerChannelName", "")
    channel_id   = vd.get("channelId", "") or ms.get("externalChannelId", "")
    dur_secs     = int(vd.get("lengthSeconds", 0) or ms.get("lengthSeconds", 0) or 0)
    raw_views    = vd.get("viewCount", "0") or "0"
    is_live      = bool(vd.get("isLive") or vd.get("isLiveContent"))
    keywords     = vd.get("keywords", [])
    upload_date  = ms.get("uploadDate") or ms.get("publishDate") or ""

    thumbs = _dig(vd, "thumbnail", "thumbnails") or _dig(ms, "thumbnail", "thumbnails") or []
    thumbnail_url = thumbs[-1]["url"] if thumbs else ""

    return {
        "video_id":           video_id,
        "title":              title,
        "description":        description,
        "duration_seconds":   dur_secs,
        "duration_formatted": _format_duration(dur_secs),
        "view_count":         int(raw_views.replace(",", "")) if raw_views else 0,
        "like_count":         0,
        "upload_date":        upload_date,
        "channel_name":       channel_name,
        "channel_id":         channel_id,
        "thumbnail_url":      thumbnail_url,
        "is_live":            is_live,
        "keywords":           keywords,
    }


def fetch_video_data(video_id: str) -> dict:
    # ---- Strategy 1: webpage scrape ----
    try:
        html = _fetch_page(f"https://www.youtube.com/watch?v={video_id}&hl=en")
        pr = _extract_yt_var(html, "ytInitialPlayerResponse")
        if pr:
            vd = pr.get("videoDetails") or {}
            if vd.get("title"):
                return _parse_player_response(pr, video_id)
    except (RateLimitError, httpx.HTTPStatusError):
        raise
    except Exception:
        pass

    # ---- Strategy 2: android_vr / tv_simply InnerTube ----
    for ctx, ctx_name in [(_CTX_ANDROID_VR, "android_vr"), (_CTX_TV_SIMPLY, "tv_simply")]:
        try:
            pr = _innertube_post(
                "player",
                {"videoId": video_id, "params": "2AMBCgIQBg=="},
                context=ctx,
            )
            vd = pr.get("videoDetails") or {}
            if vd.get("title"):
                return _parse_player_response(pr, video_id)
        except (RateLimitError, httpx.HTTPStatusError):
            raise
        except Exception:
            continue

    raise VideoNotFoundError(
        f"Video {video_id!r} could not be fetched. "
        "It may be private, deleted, or region-restricted."
    )


# ---------------------------------------------------------------------------
# Playlist data fetching
# ---------------------------------------------------------------------------

def _parse_playlist_video_renderer(r: dict) -> Optional[dict]:
    video_id = r.get("videoId")
    if not video_id:
        return None
    title      = _simple_or_runs(r.get("title"))
    dur_text   = _simple_or_runs(r.get("lengthText"))
    dur_secs   = _duration_to_seconds(dur_text)
    channel    = _runs_text(r.get("shortBylineText") or {})
    channel_id = _dig(r, "shortBylineText", "runs", 0, "navigationEndpoint",
                      "browseEndpoint", "browseId") or ""
    thumbs = _dig(r, "thumbnail", "thumbnails") or []
    thumbnail_url = thumbs[-1]["url"] if thumbs else ""
    return {
        "video_id":           video_id,
        "title":              title,
        "duration_seconds":   dur_secs,
        "duration_formatted": _format_duration(dur_secs) if dur_secs else "",
        "channel_name":       channel,
        "channel_id":         channel_id,
        "thumbnail_url":      thumbnail_url,
        "_partial":           True,
    }


def _parse_lockup_view_model(lv: dict) -> Optional[dict]:
    video_id = (
        _dig(lv, "rendererContext", "commandContext", "onTap",
             "innertubeCommand", "watchEndpoint", "videoId")
        or _dig(lv, "contentImage", "thumbnailViewModel", "overlays", 0,
                "thumbnailBottomOverlayViewModel", "badges", 0,
                "thumbnailBadgeViewModel", "animationActivationTargetId")
    )
    if not video_id:
        return None
    title    = _dig(lv, "metadata", "lockupMetadataViewModel", "title", "content") or ""
    dur_text = (
        _dig(lv, "contentImage", "thumbnailViewModel", "overlays", 0,
             "thumbnailBottomOverlayViewModel", "badges", 0,
             "thumbnailBadgeViewModel", "text") or ""
    )
    dur_secs   = _duration_to_seconds(dur_text)
    channel    = (
        _dig(lv, "metadata", "lockupMetadataViewModel", "metadata",
             "contentMetadataViewModel", "metadataRows", 0,
             "metadataParts", 0, "text", "content") or ""
    )
    channel_id = (
        _dig(lv, "metadata", "lockupMetadataViewModel", "metadata",
             "contentMetadataViewModel", "metadataRows", 0,
             "metadataParts", 0, "text", "commandRuns", 0, "onTap",
             "innertubeCommand", "browseEndpoint", "browseId") or ""
    )
    thumbs = _dig(lv, "contentImage", "thumbnailViewModel", "image", "sources") or []
    thumbnail_url = thumbs[-1]["url"] if thumbs else ""
    return {
        "video_id":           video_id,
        "title":              title,
        "duration_seconds":   dur_secs,
        "duration_formatted": _format_duration(dur_secs) if dur_secs else dur_text,
        "channel_name":       channel,
        "channel_id":         channel_id,
        "thumbnail_url":      thumbnail_url,
        "_partial":           True,
    }


def _parse_item_stub(item: dict) -> Optional[dict]:
    if "playlistVideoRenderer" in item:
        return _parse_playlist_video_renderer(item["playlistVideoRenderer"])
    if "lockupViewModel" in item:
        return _parse_lockup_view_model(item["lockupViewModel"])
    return None


def _get_continuation_token(item: dict) -> Optional[str]:
    cir = item.get("continuationItemRenderer") or {}
    ep  = cir.get("continuationEndpoint") or {}
    t = _dig(ep, "continuationCommand", "token")
    if t:
        return t
    commands = _dig(ep, "commandExecutorCommand", "commands") or []
    for cmd in commands:
        t = _dig(cmd, "continuationCommand", "token")
        if t:
            return t
    return None


def _collect_playlist_items(items: list) -> tuple[list[dict], Optional[str]]:
    stubs: list[dict] = []
    token: Optional[str] = None
    for item in items:
        stub = _parse_item_stub(item)
        if stub:
            stubs.append(stub)
        elif "continuationItemRenderer" in item:
            t = _get_continuation_token(item)
            if t:
                token = t
    return stubs, token


def _playlist_section_items(section_contents: list) -> tuple[list[dict], Optional[str]]:
    stubs: list[dict] = []
    token: Optional[str] = None
    for section in section_contents:
        if "itemSectionRenderer" not in section:
            continue
        isr_contents = section["itemSectionRenderer"].get("contents") or []
        list_contents: Optional[list] = None
        for child in isr_contents:
            if "playlistVideoListRenderer" in child:
                list_contents = child["playlistVideoListRenderer"].get("contents") or []
                break
        if list_contents is not None:
            new_stubs, inner_token = _collect_playlist_items(list_contents)
        else:
            new_stubs, inner_token = _collect_playlist_items(isr_contents)
        stubs.extend(new_stubs)
        if inner_token:
            token = inner_token
    return stubs, token


def _parse_playlist_video_count(data: dict, stub_count: int) -> int:
    stats = (
        _dig(data, "sidebar", "playlistSidebarRenderer", "items", 0,
             "playlistSidebarPrimaryInfoRenderer", "stats") or []
    )
    for stat in stats:
        text = _runs_text(stat) or _simple_or_runs(stat)
        if text and "video" in text.lower():
            m = re.search(r"([\d,]+)", text.replace("\xa0", " "))
            if m:
                return int(m.group(1).replace(",", ""))
    for key in ("numVideosText", "bylineText", "briefBylineText"):
        text = _simple_or_runs(_dig(data, "header", "playlistHeaderRenderer", key))
        if text and "video" in text.lower():
            m = re.search(r"([\d,]+)", text.replace("\xa0", " "))
            if m:
                return int(m.group(1).replace(",", ""))
    return stub_count


def _parse_playlist_views(data: dict) -> int:
    """
    Extract the total view count for a playlist from the YouTube response data.
    
    YouTube displays playlist views in various formats like:
    - "1,234,567 views"
    - "1.2M views"
    - "1,234 views"
    
    This function searches through the stats in the sidebar and header
    to find the view count.
    
    Parameters
    ----------
    data : dict
        The raw YouTube API response data.
    
    Returns
    -------
    int
        The total number of views, or 0 if not found.
    """
    # Try to find views in sidebar stats
    stats = (
        _dig(data, "sidebar", "playlistSidebarRenderer", "items", 0,
             "playlistSidebarPrimaryInfoRenderer", "stats") or []
    )
    for stat in stats:
        text = _runs_text(stat) or _simple_or_runs(stat)
        if text and "view" in text.lower():
            # Handle formats like "1,234,567 views" or "1.2M views"
            text_clean = text.replace("\xa0", " ").replace(",", "")
            # Check for K/M/B suffixes
            multiplier = 1
            if "K" in text_clean.upper():
                multiplier = 1_000
                text_clean = text_clean.upper().replace("K", "")
            elif "M" in text_clean.upper():
                multiplier = 1_000_000
                text_clean = text_clean.upper().replace("M", "")
            elif "B" in text_clean.upper():
                multiplier = 1_000_000_000
                text_clean = text_clean.upper().replace("B", "")
            m = re.search(r"([\d.]+)", text_clean)
            if m:
                try:
                    return int(float(m.group(1)) * multiplier)
                except ValueError:
                    pass
    
    # Try header stats
    header = _dig(data, "header", "playlistHeaderRenderer") or {}
    for key in ("stats", "bylineText", "briefBylineText"):
        if key == "stats":
            header_stats = header.get(key) or []
            for stat in header_stats:
                text = _runs_text(stat) or _simple_or_runs(stat)
                if text and "view" in text.lower():
                    text_clean = text.replace("\xa0", " ").replace(",", "")
                    multiplier = 1
                    if "K" in text_clean.upper():
                        multiplier = 1_000
                        text_clean = text_clean.upper().replace("K", "")
                    elif "M" in text_clean.upper():
                        multiplier = 1_000_000
                        text_clean = text_clean.upper().replace("M", "")
                    elif "B" in text_clean.upper():
                        multiplier = 1_000_000_000
                        text_clean = text_clean.upper().replace("B", "")
                    m = re.search(r"([\d.]+)", text_clean)
                    if m:
                        try:
                            return int(float(m.group(1)) * multiplier)
                        except ValueError:
                            pass
        else:
            text = _simple_or_runs(header.get(key))
            if text and "view" in text.lower():
                text_clean = text.replace("\xa0", " ").replace(",", "")
                multiplier = 1
                if "K" in text_clean.upper():
                    multiplier = 1_000
                    text_clean = text_clean.upper().replace("K", "")
                elif "M" in text_clean.upper():
                    multiplier = 1_000_000
                    text_clean = text_clean.upper().replace("M", "")
                elif "B" in text_clean.upper():
                    multiplier = 1_000_000_000
                    text_clean = text_clean.upper().replace("B", "")
                m = re.search(r"([\d.]+)", text_clean)
                if m:
                    try:
                        return int(float(m.group(1)) * multiplier)
                    except ValueError:
                        pass
    
    return 0


def fetch_playlist_data(
    playlist_id: str,
    max_videos: int = 0,
    session: Optional[YoutubeSession] = None,
) -> dict:

    def _continuation_items(resp: dict) -> list:
        actions = resp.get("onResponseReceivedActions") or []
        for action in actions:
            items = _dig(action, "appendContinuationItemsAction", "continuationItems")
            if items:
                return items
        return []

    data = _innertube_post("browse", {"browseId": f"VL{playlist_id}"}, session=session)

    for alert in (data.get("alerts") or []):
        r = alert.get("alertRenderer") or {}
        if r.get("type", "").upper() == "ERROR":
            msg = _simple_or_runs(r.get("text")) or "Unknown error"
            raise PlaylistNotFoundError(f"Playlist {playlist_id!r}: {msg}")

    header  = _dig(data, "header", "playlistHeaderRenderer") or {}
    pl_meta = _dig(data, "metadata", "playlistMetadataRenderer") or {}

    title = (
        _simple_or_runs(header.get("title"))
        or _dig(data, "sidebar", "playlistSidebarRenderer", "items", 0,
                "playlistSidebarPrimaryInfoRenderer", "title", "runs", 0, "text")
        or pl_meta.get("title", "")
    )
    description = (
        _simple_or_runs(header.get("descriptionText"))
        or pl_meta.get("description", "")
    )
    owner = _runs_text(header.get("ownerText") or {})
    owner_id = _dig(header, "ownerText", "runs", 0,
                    "navigationEndpoint", "browseEndpoint", "browseId") or ""
    owner_handle = None
    
    # Try to get owner from sidebar secondary info videoOwnerRenderer (items[1])
    if not owner:
        owner_renderer = _dig(data, "sidebar", "playlistSidebarRenderer", "items", 1,
                              "playlistSidebarSecondaryInfoRenderer", "videoOwner",
                              "videoOwnerRenderer") or {}
        if owner_renderer:
            # Get display name
            owner = _runs_text(owner_renderer.get("title")) or ""
            # Get handle from navigationEndpoint
            handle_url = _dig(owner_renderer, "navigationEndpoint", "browseEndpoint", "canonicalBaseUrl") or ""
            if handle_url.startswith("/@"):
                owner_handle = handle_url[1:]  # Remove leading "/" to get "@Handle"
            elif handle_url.startswith("/"):
                # Could be /channel/UC... or /c/Handle or /user/Username
                handle_url = handle_url[1:]  # Remove leading "/"
                if handle_url.startswith("channel/"):
                    owner_id = handle_url.split("/")[1]
                else:
                    owner_handle = f"@{handle_url}"
    
    # Try sidebar primary info videoOwnerRenderer (items[0]) if still not found
    if not owner:
        owner_renderer = _dig(data, "sidebar", "playlistSidebarRenderer", "items", 0,
                              "playlistSidebarPrimaryInfoRenderer", "videoOwner",
                              "videoOwnerRenderer") or {}
        if owner_renderer:
            owner = _runs_text(owner_renderer.get("title")) or ""
            handle_url = _dig(owner_renderer, "navigationEndpoint", "browseEndpoint", "canonicalBaseUrl") or ""
            if handle_url.startswith("/@"):
                owner_handle = handle_url[1:]
            elif handle_url.startswith("/"):
                handle_url = handle_url[1:]
                if handle_url.startswith("channel/"):
                    owner_id = handle_url.split("/")[1]
                else:
                    owner_handle = f"@{handle_url}"
    
    # Fallback: try header ownerText
    if not owner:
        owner = _runs_text(header.get("ownerText") or {})
    
    # Fallback: try bylineText which sometimes contains owner info
    if not owner:
        byline = _dig(header, "bylineText", "runs") or []
        for run in byline:
            text = run.get("text", "")
            if text and text.strip():
                owner = text.strip()
                break
    
    # Fallback: try stats in sidebar
    if not owner:
        stats = (
            _dig(data, "sidebar", "playlistSidebarRenderer", "items", 0,
                 "playlistSidebarPrimaryInfoRenderer", "stats") or []
        )
        for stat in stats:
            text = _runs_text(stat) or _simple_or_runs(stat)
            if text and ("by " in text.lower() or "channel" in text.lower()):
                # Extract channel name from text like "by ChannelName"
                parts = text.split("by ")
                if len(parts) > 1:
                    owner = parts[-1].strip()
                    break
    
    # Also try to get owner_id from sidebar secondary info if not found
    if not owner_id:
        owner_id = (
            _dig(data, "sidebar", "playlistSidebarRenderer", "items", 1,
                 "playlistSidebarSecondaryInfoRenderer", "videoOwner",
                 "videoOwnerRenderer", "navigationEndpoint", "browseEndpoint", "browseId") or ""
        )
    
    # Clean up owner name - remove "by " prefix if present
    if owner and owner.lower().startswith("by "):
        owner = owner[3:].strip()

    thumbs = (
        _dig(header, "thumbnail", "thumbnails")
        or _dig(header, "playlistHeaderBanner", "heroPlaylistThumbnailRenderer",
                "thumbnail", "thumbnails")
        or []
    )
    thumbnail_url = thumbs[-1]["url"] if thumbs else ""
    last_updated  = _simple_or_runs(header.get("bylineText")) or ""

    section_contents = (
        _dig(data, "contents", "twoColumnBrowseResultsRenderer",
             "tabs", 0, "tabRenderer", "content", "sectionListRenderer", "contents")
        or _dig(data, "contents", "singleColumnBrowseResultsRenderer",
                "tabs", 0, "tabRenderer", "content", "sectionListRenderer", "contents")
        or []
    )

    stubs, token = _playlist_section_items(section_contents)

    seen_tokens:    set[str] = set()
    seen_video_ids: set[str] = {s["video_id"] for s in stubs if s.get("video_id")}

    while token and token not in seen_tokens:
        if max_videos and len(stubs) >= max_videos:
            break
        seen_tokens.add(token)
        resp  = _innertube_post("browse", {"continuation": token}, session=session)
        items = _continuation_items(resp)
        if not items:
            break
        new_stubs, token = _collect_playlist_items(items)
        if not new_stubs:
            break
        for stub in new_stubs:
            vid = stub.get("video_id")
            if vid and vid in seen_video_ids:
                continue
            if vid:
                seen_video_ids.add(vid)
            stubs.append(stub)

    if max_videos:
        stubs = stubs[:max_videos]

    total_count = _parse_playlist_video_count(data, len(stubs))
    total_views = _parse_playlist_views(data)

    return {
        "playlist_id":   playlist_id,
        "title":         title,
        "description":   description,
        "video_count":   total_count,
        "owner":         owner,
        "owner_id":      owner_id,
        "owner_handle":  owner_handle,
        "thumbnail_url": thumbnail_url,
        "last_updated":  last_updated,
        "views":         total_views,
        "videos":        stubs,
    }


# ---------------------------------------------------------------------------
# Authenticated playlist mutations
# ---------------------------------------------------------------------------

def edit_playlist(
    playlist_id: str,
    actions: list[dict],
    session: Optional[YoutubeSession] = None,
) -> dict:
    """Execute playlist edit actions (add/remove/reorder videos). Requires auth."""
    return _innertube_post(
        "browse/edit_playlist",
        {"playlistId": playlist_id, "actions": actions},
        session=session,
        require_auth=True,
    )


def add_video_to_playlist(
    playlist_id: str,
    video_id: str,
    session: Optional[YoutubeSession] = None,
) -> dict:
    """Add a single video to a playlist. Requires authentication."""
    video_id = extract_video_id(video_id)
    return edit_playlist(
        playlist_id,
        [{"addedVideoId": video_id, "action": "ACTION_ADD_VIDEO"}],
        session=session,
    )


def remove_video_from_playlist(
    playlist_id: str,
    video_id: str,
    session: Optional[YoutubeSession] = None,
) -> dict:
    """Remove a video from a playlist. Requires authentication."""
    video_id = extract_video_id(video_id)
    return edit_playlist(
        playlist_id,
        [{"action": "ACTION_REMOVE_VIDEO_BY_VIDEO_ID", "removedVideoId": video_id}],
        session=session,
    )


def create_playlist(
    title: str,
    video_ids: Optional[list[str]] = None,
    session: Optional[YoutubeSession] = None,
) -> dict:
    """Create a new playlist owned by the authenticated user."""
    ids = [extract_video_id(v) for v in (video_ids or [])]
    return _innertube_post(
        "playlist/create",
        {"title": title, "videoIds": ids},
        session=session,
        require_auth=True,
    )


# ---------------------------------------------------------------------------
# Channel / Creator data fetching
# ---------------------------------------------------------------------------

_YT_INITIAL_DATA_RE = re.compile(
    r'(?:var\s+ytInitialData\s*=\s*|window\["ytInitialData"\]\s*=\s*|ytInitialData\s*=\s*)'
    r'(\{.*?\})\s*;',
    re.S,
)

_EXTERNAL_CHANNEL_ID_RE = re.compile(r'"externalChannelId"\s*:\s*"(?P<id>UC[^"]+)"')


def _extract_yt_initial_data(page_html: str) -> dict[str, Any]:
    m = _YT_INITIAL_DATA_RE.search(page_html)
    if not m:
        raise ParseError("ytInitialData not found in channel HTML")
    raw_json = html_lib.unescape(m.group(1))
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise ParseError("Failed to parse ytInitialData") from e


def _parse_channel_page(html_text: str, handle_or_id: str) -> dict:
    initial  = _extract_yt_initial_data(html_text)
    metadata = _dig(initial, "metadata", "channelMetadataRenderer") or {}
    header   = (
        _dig(initial, "header", "c4TabbedHeaderRenderer")
        or _dig(initial, "header", "pageHeaderRenderer")
        or {}
    )
    channel_id = (
        metadata.get("externalId")
        or (_EXTERNAL_CHANNEL_ID_RE.search(html_text).group("id")
            if _EXTERNAL_CHANNEL_ID_RE.search(html_text) else "")
    )
    if not channel_id:
        raise ParseError(f"Channel not found: {handle_or_id!r}")

    channel_name  = _simple_or_runs(header.get("title")) or metadata.get("title") or ""
    description   = metadata.get("description") or ""
    sub_text      = _simple_or_runs(header.get("subscriberCountText")) or ""
    avatar_thumbs = _dig(header, "avatar", "thumbnails") or []
    avatar_url    = avatar_thumbs[-1]["url"] if avatar_thumbs else ""
    banner_thumbs = (
        _dig(header, "banner", "thumbnails")
        or _dig(header, "banner", "image", "thumbnails")
        or []
    )
    banner_url            = banner_thumbs[-1]["url"] if banner_thumbs else ""
    uploads_playlist_id   = f"UU{channel_id[2:]}" if channel_id.startswith("UC") else None

    return {
        "channel_id":           channel_id,
        "channel_name":         channel_name,
        "description":          description,
        "subscriber_text":      sub_text,
        "avatar_url":           avatar_url,
        "banner_url":           banner_url,
        "uploads_playlist_id":  uploads_playlist_id,
    }


def resolve_channel_handle(url_or_id: str) -> str:
    """
    Resolve any channel identifier to the actual handle (without @ prefix).
    
    Uses the InnerTube API and HTML scraping to fetch the handle from the channel metadata.
    This is more reliable than regex extraction from URLs.
    
    Parameters
    ----------
    url_or_id : str
        Any of: full channel URL, @Handle, UCxxxx channel ID, or vanity name.
    
    Returns
    -------
    str
        The channel handle without @ prefix (e.g., 'MrBeast').
    """
    # First, extract a browse ID from the input
    browse_id = _extract_browse_id(url_or_id)
    
    # For UC IDs, use InnerTube API
    if browse_id.startswith("UC") and len(browse_id) > 10:
        return _resolve_handle_from_channel_id(browse_id)
    
    # For handles (with or without @), fetch the channel page HTML
    # and extract the canonical handle from ytInitialData
    handle_or_id = browse_id
    if not handle_or_id.startswith("@"):
        handle_or_id = "@" + handle_or_id.lstrip("@")
    
    try:
        html_text = _fetch_page(f"https://www.youtube.com/{handle_or_id}")
        initial = _extract_yt_initial_data(html_text)
        metadata = _dig(initial, "metadata", "channelMetadataRenderer") or {}
        
        # Try to get vanity URL which contains the handle
        vanity_url = metadata.get("vanityChannelUrl", "")
        if vanity_url:
            handle = _extract_handle_from_url(vanity_url)
            if handle:
                return handle
        
        # Try to get channel URL
        channel_url = metadata.get("channelUrl", "")
        if channel_url:
            handle = _extract_handle_from_url(channel_url)
            if handle:
                return handle
        
        # Check header for handle
        header = (
            _dig(initial, "header", "c4TabbedHeaderRenderer")
            or _dig(initial, "header", "pageHeaderRenderer")
            or {}
        )
        
        # Check metadata parts in page header
        metadata_rows = _dig(header, "metadata", "contentMetadataViewModel", "metadataRows") or []
        for row in metadata_rows:
            parts = row.get("metadataParts") or []
            for part in parts:
                text_content = _dig(part, "text", "content") or ""
                if text_content.startswith("@"):
                    return text_content[1:]
        
        # Check byline text
        byline = _dig(header, "bylineText", "runs") or []
        for run in byline:
            text = run.get("text", "")
            if text.startswith("@"):
                return text[1:]
            
    except Exception:
        pass
    
    # Fallback: return the handle without @ prefix
    if browse_id.startswith("@"):
        return browse_id[1:]
    
    return browse_id


def _resolve_handle_from_channel_id(channel_id: str) -> str:
    """
    Resolve handle from a UC channel ID using InnerTube API.
    
    Parameters
    ----------
    channel_id : str
        The UC channel ID.
    
    Returns
    -------
    str
        The channel handle without @ prefix, or the channel ID if handle not found.
    """
    try:
        data = _innertube_post("browse", {"browseId": channel_id})
        metadata = _dig(data, "metadata", "channelMetadataRenderer") or {}
        
        # Try to get vanity URL which contains the handle
        vanity_url = metadata.get("vanityChannelUrl", "")
        if vanity_url:
            handle = _extract_handle_from_url(vanity_url)
            if handle:
                return handle
        
        # Try channel URL
        channel_url = metadata.get("channelUrl", "")
        if channel_url:
            handle = _extract_handle_from_url(channel_url)
            if handle:
                return handle
        
        # Check header for handle
        header = (
            _dig(data, "header", "c4TabbedHeaderRenderer")
            or _dig(data, "header", "pageHeaderRenderer")
            or {}
        )
        
        # Check metadata parts in page header
        metadata_rows = _dig(header, "metadata", "contentMetadataViewModel", "metadataRows") or []
        for row in metadata_rows:
            parts = row.get("metadataParts") or []
            for part in parts:
                text_content = _dig(part, "text", "content") or ""
                if text_content.startswith("@"):
                    return text_content[1:]
        
        # Check byline text
        byline = _dig(header, "bylineText", "runs") or []
        for run in byline:
            text = run.get("text", "")
            if text.startswith("@"):
                return text[1:]
                
    except Exception:
        pass
    
    # Fallback: return the channel ID
    return channel_id


def _extract_browse_id(url_or_id: str) -> str:
    """
    Extract a browse ID from any channel identifier.
    
    Returns a value suitable for use as browseId in InnerTube API calls.
    """
    # Check for channel ID (UC...)
    if url_or_id.startswith("UC") and len(url_or_id) > 10:
        return url_or_id
    
    # Check for handle URL or @handle
    if url_or_id.startswith("@"):
        return url_or_id
    
    # Check for full URL
    m = _CHANNEL_RE.search(url_or_id)
    if m:
        handle, uc_id, c_name, user = m.groups()
        if handle:
            return f"@{handle}"
        if uc_id:
            return uc_id
        if c_name:
            return c_name
        if user:
            return user
    
    # Check for channel/ID URL format
    if "/channel/UC" in url_or_id:
        m = re.search(r"/channel/(UC[a-zA-Z0-9_-]+)", url_or_id)
        if m:
            return m.group(1)
    
    # If it's not a URL, treat as handle
    if not url_or_id.startswith("http"):
        return f"@{url_or_id}"
    
    raise ValueError(f"Cannot extract browse ID from {url_or_id!r}")


def _extract_handle_from_url(url: str) -> Optional[str]:
    """Extract handle (without @) from a URL like 'https://www.youtube.com/@MrBeast'."""
    if not url:
        return None
    m = re.search(r"/@([^/?#\s]+)", url)
    if m:
        return m.group(1)
    return None


def fetch_channel_data(handle_or_id: str) -> dict:
    """Fetch channel metadata. Accepts '@Handle', 'UCxxxxx', or a vanity name."""
    if handle_or_id.startswith("UC") and len(handle_or_id) > 10:
        data = _innertube_post("browse", {"browseId": handle_or_id})
        for alert in (data.get("alerts") or []):
            alert_r = alert.get("alertRenderer") or {}
            if alert_r.get("type", "").upper() == "ERROR":
                raise ParseError(f"Channel not found: {handle_or_id!r}")
        header     = (
            _dig(data, "header", "c4TabbedHeaderRenderer")
            or _dig(data, "header", "pageHeaderRenderer")
            or {}
        )
        channel_name = (
            _simple_or_runs(header.get("title"))
            or _simple_or_runs(_dig(header, "pageTitle"))
            or ""
        )
        channel_id  = _dig(data, "metadata", "channelMetadataRenderer", "externalId") or ""
        description = _dig(data, "metadata", "channelMetadataRenderer", "description") or ""
        sub_text    = _simple_or_runs(header.get("subscriberCountText")) or ""
        avatar_thumbs = _dig(header, "avatar", "thumbnails") or []
        avatar_url    = avatar_thumbs[-1]["url"] if avatar_thumbs else ""
        banner_thumbs = _dig(data, "header", "c4TabbedHeaderRenderer", "banner", "thumbnails") or []
        banner_url    = banner_thumbs[-1]["url"] if banner_thumbs else ""
        uploads_playlist_id = f"UU{channel_id[2:]}" if channel_id.startswith("UC") else None
        return {
            "channel_id":           channel_id,
            "channel_name":         channel_name,
            "description":          description,
            "subscriber_text":      sub_text,
            "avatar_url":           avatar_url,
            "banner_url":           banner_url,
            "uploads_playlist_id":  uploads_playlist_id,
        }

    if not handle_or_id.startswith("@"):
        handle_or_id = "@" + handle_or_id.lstrip("@")
    html_text = _fetch_page(f"https://www.youtube.com/{handle_or_id}")
    return _parse_channel_page(html_text, handle_or_id)
