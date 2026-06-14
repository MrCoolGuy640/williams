from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Iterator, Optional

from ._internal import _innertube
from .exceptions import CreatorNotFoundError

if TYPE_CHECKING:
    from .playlist import YoutubePlaylist
    from .video import YoutubeVideo

class YoutubeCreator:
    """
    Represents a YouTube channel / creator.

    Parameters
    ----------
    url_or_id : str
        Any of: full channel URL, ``@Handle``, ``UCxxxx`` channel ID,
        or a vanity URL slug.

    Examples
    --------
    >>> creator = YoutubeCreator("https://www.youtube.com/@LinusTechTips")
    >>> print(creator.name, creator.subscriber_count_text)
    >>> for video in creator.iter_videos(max_videos=10):
    ...     print(video.title)
    """

    def __init__(self, url_or_id: str) -> None:
        # Use InnerTube API to resolve the handle correctly
        # This ensures we always get the actual handle (without @) regardless of input format
        self._handle = _innertube.resolve_channel_handle(url_or_id)
        self._lock = threading.Lock()
        self._data: Optional[dict] = None

    # ------------------------------------------------------------------
    # Internal loading
    # ------------------------------------------------------------------

    def _ensure_data(self) -> None:
        if self._data is not None:
            return
        with self._lock:
            if self._data is not None:
                return
            data = _innertube.fetch_channel_data(self._handle)
            if not data.get("channel_id") and not data.get("channel_name"):
                raise CreatorNotFoundError(f"Channel not found: {self._handle!r}")
            self._data = data

    def _d(self) -> dict:
        self._ensure_data()
        assert self._data is not None
        return self._data

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def channel_id(self) -> str:
        return self._d().get("channel_id", "")

    @property
    def handle(self) -> str:
        return self._handle

    def get_handle_url(self) -> str:
        """
        Return the handle-based URL for this channel (e.g., https://www.youtube.com/@Handle).
        
        Returns
        -------
        str
            The handle-based URL. If the handle is not available, falls back to the
            channel ID URL.
        """
        # Handle is stored without @ prefix, so construct the handle URL
        if self._handle.startswith("@"):
            return f"https://www.youtube.com/{self._handle}"
        # We have a handle (without @), construct the handle URL
        return f"https://www.youtube.com/@{self._handle}"

    def get_id_url(self) -> str:
        """
        Return the channel ID-based URL for this channel (e.g., https://www.youtube.com/channel/UC...).
        
        Returns
        -------
        str
            The channel ID-based URL. If the channel ID is not available, falls back
            to the handle URL.
        """
        cid = self.channel_id
        if cid:
            return f"https://www.youtube.com/channel/{cid}"
        # Fallback to handle URL if channel ID is not available
        if self._handle.startswith("@"):
            return f"https://www.youtube.com/{self._handle}"
        return f"https://www.youtube.com/@{self._handle}"

    def __repr__(self) -> str:
        name = self._data.get("channel_name", "?") if self._data else "?"
        return f"YoutubeCreator(handle={self._handle!r}, name={name!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, YoutubeCreator):
            return self.channel_id == other.channel_id
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.channel_id or self._handle)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Channel display name."""
        return self._d().get("channel_name", "")

    @property
    def description(self) -> str:
        """Channel description."""
        return self._d().get("description", "")

    @property
    def subscriber_count_text(self) -> str:
        """Subscriber count as YouTube displays it, e.g. '15.8M subscribers'."""
        return self._d().get("subscriber_text", "")

    @property
    def avatar_url(self) -> str:
        """URL of the channel avatar image."""
        return self._d().get("avatar_url", "")

    @property
    def banner_url(self) -> str:
        """URL of the channel banner image."""
        return self._d().get("banner_url", "")

    @property
    def uploads_playlist_id(self) -> Optional[str]:
        """The 'UU…' playlist ID containing all uploads."""
        return self._d().get("uploads_playlist_id")

    @property
    def video_count(self) -> int:
        """
        Total number of public videos.

        Fetched from the uploads playlist length (most reliable source).
        """
        pl_id = self.uploads_playlist_id
        if not pl_id:
            return 0
        pl = self.get_uploads_playlist()
        return pl.video_count

    def get_metadata(self) -> dict:
        """Return channel metadata as a plain dict."""
        return {
            "channel_id":        self.channel_id,
            "handle":            self._handle,
            "handle_url":        self.get_handle_url(),
            "id_url":            self.get_id_url(),
            "name":              self.name,
            "description":       self.description,
            "subscriber_text":   self.subscriber_count_text,
            "avatar_url":        self.avatar_url,
            "banner_url":        self.banner_url,
            "uploads_playlist_id": self.uploads_playlist_id,
        }

    # ------------------------------------------------------------------
    # Video access
    # ------------------------------------------------------------------


    def get_uploads_playlist(self) -> YoutubePlaylist:
        """Return the channel's uploads as a :class:`YoutubePlaylist`."""
        from williams.apis.youtube.playlist import YoutubePlaylist
        
        pl_id = self.uploads_playlist_id
        if not pl_id:
            raise CreatorNotFoundError(
                f"Cannot determine uploads playlist for {self._handle!r}."
            )
        return YoutubePlaylist(pl_id)

    def iter_videos(
        self,
        max_videos: int = 0,
    ) -> Iterator[YoutubeVideo]:
        """
        Iterate over this channel's uploaded videos (most recent first).

        Like :meth:`YoutubePlaylist.iter_videos`, each video is pre-seeded
        with title/duration from the playlist response so no per-video HTTP
        calls are made for those fields.

        Parameters
        ----------
        max_videos : int
            Stop after this many videos (0 = all).

        Yields
        ------
        YoutubeVideo
        """
        pl = self.get_uploads_playlist()
        yield from pl.iter_videos(max_videos=max_videos)

    def get_videos(
        self,
        max_videos: int = 0,
        prefetch_metadata: bool = False,
        workers: int = 8,
    ) -> list[YoutubeVideo]:
        """
        Return a list of this channel's videos.

        Parameters
        ----------
        max_videos : int
            Maximum videos to return (0 = all).
        prefetch_metadata : bool
            Eagerly fetch full metadata for each video in parallel.
        workers : int
            Thread-pool size for ``prefetch_metadata=True``.
        """
        pl = self.get_uploads_playlist()
        return pl.get_videos(
            max_videos=max_videos,
            prefetch_metadata=prefetch_metadata,
            workers=workers,
        )

    def reload(self) -> YoutubeCreator:
        """Bust the cache and re-fetch channel data. Returns self."""
        with self._lock:
            self._data = None
        return self