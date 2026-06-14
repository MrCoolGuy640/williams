"""Custom exceptions for the YouTube library."""


class YouTubeError(Exception):
    """Base exception for all library errors."""


class VideoNotFoundError(YouTubeError):
    """Raised when a video cannot be found or is unavailable."""


class PlaylistNotFoundError(YouTubeError):
    """Raised when a playlist cannot be found or is private."""


class CreatorNotFoundError(YouTubeError):
    """Raised when a channel / creator cannot be found."""


class RateLimitError(YouTubeError):
    """Raised when YouTube returns 429 or equivalent throttling."""


class ParseError(YouTubeError):
    """Raised when expected data cannot be parsed from a response."""


class MediaError(YouTubeError):
    """Raised when a media operation fails (download, frame extract, etc.)."""


class DownloadError(MediaError):
    """Raised when a video/audio download fails."""


class AuthenticationError(YouTubeError):
    """Raised when authenticated requests fail due to missing/invalid cookies."""