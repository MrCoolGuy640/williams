import pytest

from williams.apis.youtube import YoutubePlaylist, YoutubeVideo, YoutubeCreator


# Example public playlist URL (YouTube Music Top 100)
PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj"


def test_playlist_basic_properties():
    playlist = YoutubePlaylist(PLAYLIST_URL)
    # Title and ID should be non-empty strings
    assert isinstance(playlist.title, str) and playlist.title
    assert isinstance(playlist.playlist_id, str) and playlist.playlist_id
    assert playlist.url == PLAYLIST_URL
    # Video count should be a positive integer for a public playlist
    count = playlist.video_count
    assert isinstance(count, int) and count > 0
    # Owner information should be a string (may be empty for system playlists like YouTube Music)
    owner = playlist.owner
    assert isinstance(owner, str) and playlist.owner
    assert isinstance(playlist.get_owner_creator(), YoutubeCreator)
    # Retrieve the first video and verify its type
    first_video = playlist.get_video_at_index(0)
    assert isinstance(first_video, YoutubeVideo)


def test_playlist_views():
    """Test that playlist views can be retrieved."""
    playlist = YoutubePlaylist(PLAYLIST_URL)
    # Views should be a non-negative integer
    views = playlist.views
    assert isinstance(views, int) and views >= 0
    # get_playlist_views() method should return the same value
    assert playlist.get_playlist_views() == views


def test_playlist_owner_id():
    """Test that playlist owner_id can be retrieved."""
    playlist = YoutubePlaylist(PLAYLIST_URL)
    # owner_id should be a string (may be empty for some playlists)
    assert isinstance(playlist.owner_id, str)


def test_playlist_get_owner_creator():
    """Test that get_owner_creator returns a YoutubeCreator object."""
    from williams.apis.youtube import YoutubeCreator
    
    playlist = YoutubePlaylist(PLAYLIST_URL)
    # Only test if owner information is available
    if playlist.owner_id or playlist.owner:
        owner = playlist.get_owner_creator()
        assert isinstance(owner, YoutubeCreator)


def test_playlist_metadata():
    """Test that playlist metadata dict includes all expected keys."""
    playlist = YoutubePlaylist(PLAYLIST_URL)
    metadata = playlist.get_metadata()
    
    assert "playlist_id" in metadata
    assert "url" in metadata
    assert "title" in metadata
    assert "video_count" in metadata
    assert "owner" in metadata
    assert "owner_id" in metadata


def test_playlist_info():
    """Test that get_info returns a PlaylistInfo object."""
    from williams.apis.youtube.playlist import PlaylistInfo
    
    playlist = YoutubePlaylist(PLAYLIST_URL)
    info = playlist.get_info()
    
    assert isinstance(info, PlaylistInfo)
    assert info.playlist_id == playlist.playlist_id
    assert info.title == playlist.title
    assert info.video_count == playlist.video_count
    assert info.owner == playlist.owner
    assert info.owner_id == playlist.owner_id