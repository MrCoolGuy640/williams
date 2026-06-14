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


# ============================================================================
# Comprehensive tests with real data
# ============================================================================

# --- Test data: (URL, expected_playlist_id, expected_title_contains, min_videos) ---
PLAYLIST_TEST_CASES = [
    # YouTube Music Top 100
    (
        "https://www.youtube.com/playlist?list=PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj",
        "PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj",
        "Pop Music",
        10,
    ),
]


@pytest.mark.parametrize(
    "url, expected_id, expected_title, min_videos",
    PLAYLIST_TEST_CASES,
    ids=[f"case_{i}" for i in range(len(PLAYLIST_TEST_CASES))],
)
def test_playlist_identity_real_data(url: str, expected_id: str, expected_title: str, min_videos: int):
    """Verify that playlist identity (ID, title) is correctly extracted from real YouTube data."""
    playlist = YoutubePlaylist(url)
    assert playlist.playlist_id == expected_id, f"Playlist ID mismatch for {url}"
    
    if expected_title:
        assert expected_title.lower() in playlist.title.lower(), f"Title mismatch for {url}: {playlist.title}"


@pytest.mark.parametrize(
    "url, expected_id, expected_title, min_videos",
    PLAYLIST_TEST_CASES,
    ids=[f"case_{i}" for i in range(len(PLAYLIST_TEST_CASES))],
)
def test_playlist_video_count_real_data(url: str, expected_id: str, expected_title: str, min_videos: int):
    """Verify that playlist has expected number of videos."""
    playlist = YoutubePlaylist(url)
    assert playlist.video_count >= min_videos, f"Video count too low for {url}: {playlist.video_count}"


@pytest.mark.parametrize(
    "url, expected_id, expected_title, min_videos",
    PLAYLIST_TEST_CASES,
    ids=[f"case_{i}" for i in range(len(PLAYLIST_TEST_CASES))],
)
def test_playlist_videos_accessible_real_data(url: str, expected_id: str, expected_title: str, min_videos: int):
    """Verify that videos in playlist are accessible."""
    playlist = YoutubePlaylist(url)
    
    # Get first video
    first_video = playlist.get_video_at_index(0)
    assert isinstance(first_video, YoutubeVideo), f"First video is not YoutubeVideo for {url}"
    
    # Verify video has basic properties
    assert isinstance(first_video.title, str)
    assert isinstance(first_video.video_id, str)


@pytest.mark.parametrize(
    "url, expected_id, expected_title, min_videos",
    PLAYLIST_TEST_CASES,
    ids=[f"case_{i}" for i in range(len(PLAYLIST_TEST_CASES))],
)
def test_playlist_metadata_complete_real_data(url: str, expected_id: str, expected_title: str, min_videos: int):
    """Verify that playlist metadata is complete."""
    playlist = YoutubePlaylist(url)
    metadata = playlist.get_metadata()
    
    assert isinstance(metadata, dict)
    assert metadata["playlist_id"] == expected_id
    assert isinstance(metadata["title"], str) and metadata["title"]
    assert isinstance(metadata["video_count"], int) and metadata["video_count"] > 0
    assert isinstance(metadata["owner"], str)
    assert isinstance(metadata["owner_id"], str)


def test_playlist_url_formats():
    """Test that various URL formats are correctly parsed."""
    test_cases = [
        ("https://www.youtube.com/playlist?list=PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj", "PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj", "PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj"),
        ("PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj", "PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj"),  # Just the ID
    ]
    
    for url, expected_id in test_cases:
        playlist = YoutubePlaylist(url)
        assert playlist.playlist_id == expected_id, f"Failed for URL: {url}"


def test_playlist_get_video_at_index():
    """Test that get_video_at_index returns correct video."""
    playlist = YoutubePlaylist(PLAYLIST_URL)
    
    # Get first video
    first_video = playlist.get_video_at_index(0)
    assert isinstance(first_video, YoutubeVideo)
    
    # Get second video
    second_video = playlist.get_video_at_index(1)
    assert isinstance(second_video, YoutubeVideo)
    
    # Videos should be different
    assert first_video.video_id != second_video.video_id


def test_playlist_get_video_count():
    """Test that get_video_count returns correct count."""
    playlist = YoutubePlaylist(PLAYLIST_URL)
    count = playlist.get_video_count()
    
    assert isinstance(count, int)
    assert count > 0
    assert count == playlist.video_count


def test_playlist_get_owner():
    """Test that get_owner returns correct owner."""
    playlist = YoutubePlaylist(PLAYLIST_URL)
    owner = playlist.get_owner()
    
    assert isinstance(owner, str)
    assert owner == playlist.owner


def test_playlist_get_owner_id():
    """Test that get_owner_id returns correct owner ID."""
    playlist = YoutubePlaylist(PLAYLIST_URL)
    owner_id = playlist.get_owner_id()
    
    assert isinstance(owner_id, str)
    assert owner_id == playlist.owner_id


def test_playlist_repr():
    """Test that repr contains useful information and loads data if not available."""
    playlist = YoutubePlaylist(PLAYLIST_URL)
    # Get repr without first accessing title property
    repr_str = repr(playlist)
    
    assert "YoutubePlaylist" in repr_str
    # The repr should include the playlist_id
    assert playlist.playlist_id in repr_str
    # The repr should have loaded the title (either the actual title or "?")
    # Since we call _ensure_data() in __repr__, it should have the title
    assert "Pop Music" in repr_str


def test_playlist_equality():
    """Test that two playlists with the same ID are considered equal."""
    playlist1 = YoutubePlaylist("https://www.youtube.com/playlist?list=PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj")
    playlist2 = YoutubePlaylist("PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj")
    
    assert playlist1 == playlist2
    assert hash(playlist1) == hash(playlist2)


def test_playlist_get_info():
    """Test that get_info returns PlaylistInfo with correct data."""
    from williams.apis.youtube.playlist import PlaylistInfo
    
    playlist = YoutubePlaylist(PLAYLIST_URL)
    info = playlist.get_info()
    
    assert isinstance(info, PlaylistInfo)
    assert info.playlist_id == playlist.playlist_id
    assert info.title == playlist.title
    assert info.video_count == playlist.video_count
    assert info.owner == playlist.owner
    assert info.owner_id == playlist.owner_id


def test_playlist_get_metadata():
    """Test that get_metadata returns all expected keys."""
    playlist = YoutubePlaylist(PLAYLIST_URL)
    metadata = playlist.get_metadata()
    
    expected_keys = {
        "playlist_id",
        "url",
        "title",
        "description",
        "video_count",
        "owner",
        "owner_id",
        "thumbnail_url",
        "last_updated",
        "views",
    }
    
    assert expected_keys.issubset(metadata.keys()), f"Missing keys: {expected_keys - metadata.keys()}"


def test_playlist_owner_creator():
    """Test that get_owner_creator returns a valid YoutubeCreator."""
    playlist = YoutubePlaylist(PLAYLIST_URL)
    
    if playlist.owner_id or playlist.owner:
        owner = playlist.get_owner_creator()
        assert isinstance(owner, YoutubeCreator)
        assert isinstance(owner.channel_id, str)
        assert isinstance(owner.name, str)


def test_playlist_multiple_videos():
    """Test accessing multiple videos from a playlist."""
    playlist = YoutubePlaylist(PLAYLIST_URL)
    
    # Get first 3 videos (or fewer if playlist is small)
    num_videos = min(3, playlist.video_count)
    videos = []
    
    for i in range(num_videos):
        video = playlist.get_video_at_index(i)
        assert isinstance(video, YoutubeVideo)
        videos.append(video)
    
    # All videos should have unique IDs
    video_ids = [v.video_id for v in videos]
    assert len(video_ids) == len(set(video_ids)), "Video IDs should be unique"


def test_playlist_description():
    """Test that playlist description is a string."""
    playlist = YoutubePlaylist(PLAYLIST_URL)
    assert isinstance(playlist.description, str)


def test_playlist_thumbnail_url():
    """Test that playlist thumbnail URL is valid."""
    playlist = YoutubePlaylist(PLAYLIST_URL)
    
    if playlist.thumbnail_url:
        assert isinstance(playlist.thumbnail_url, str)
        assert playlist.thumbnail_url.startswith("http")


def test_playlist_last_updated():
    """Test that playlist last_updated is a string."""
    playlist = YoutubePlaylist(PLAYLIST_URL)
    assert isinstance(playlist.last_updated, str)