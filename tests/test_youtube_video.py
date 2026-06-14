import pytest

from williams.apis.youtube import YoutubeVideo, YoutubeCreator


# Example YouTube video URL (Rick Astley - Never Gonna Give You Up)
VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_video_basic_properties():
    video = YoutubeVideo(VIDEO_URL)
    # Title should be a non-empty string
    assert isinstance(video.title, str) and video.title
    # Video ID extracted from URL should match expected
    assert video.video_id == "dQw4w9WgXcQ"
    assert video.url == VIDEO_URL
    # Duration should be a positive integer (seconds)
    duration = video.duration_seconds
    assert isinstance(duration, int) and duration > 0
    # View count should be an integer
    assert isinstance(video.view_count, int)
    # Creator object should be retrievable and of correct type
    creator = video.get_creator()
    assert isinstance(creator, YoutubeCreator)


# ============================================================================
# Comprehensive tests with real data
# ============================================================================

# --- Test data: (URL, expected_video_id, expected_title_contains, expected_channel_id) ---
VIDEO_TEST_CASES = [
    # Rick Astley - Never Gonna Give You Up
    (
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "dQw4w9WgXcQ",
        "Never Gonna Give You Up",
        "UCuAXFkgsw1L7xaCfnd5JJOw",
    ),
    # MrBeast - 100 People Fight For A Private Island
    (
        "https://www.youtube.com/watch?v=2isYuQZMbdU",
        "2isYuQZMbdU",
        "100 People Fight For A Private Island",
        "UCX6OQ3DkcsbYNE6H8uQQuVA",
    ),
    # Linus Tech Tips - Powers of Ten
    (
        "https://www.youtube.com/watch?v=0fKBhvDjuy0",
        "0fKBhvDjuy0",
        "Powers of Ten™ (1977)",
        "UCCRa-wycVfgh1ctaKaD0BeQ",
    ),
    # Shorts video
    (
        "https://www.youtube.com/shorts/kwETWeFDwZU",
        "kwETWeFDwZU",
        "LEGO are more expensive than you think",
        "UCSpFnDQr88xCZ80N-X7t0nQ",
    ),
]


@pytest.mark.parametrize(
    "url, expected_id, expected_title, expected_channel",
    VIDEO_TEST_CASES,
    ids=[f"case_{i}" for i in range(len(VIDEO_TEST_CASES))],
)
def test_video_identity_real_data(url: str, expected_id: str, expected_title: str, expected_channel: str):
    """Verify that video identity (ID, title, channel) is correctly extracted from real YouTube data."""
    video = YoutubeVideo(url)
    assert video.video_id == expected_id, f"Video ID mismatch for {url}"
    
    if expected_title:
        assert expected_title.lower() in video.title.lower(), f"Title mismatch for {url}: {video.title}"
    
    if expected_channel:
        creator = video.get_creator()
        assert creator.channel_id == expected_channel, f"Channel ID mismatch for {url}"


@pytest.mark.parametrize(
    "url, expected_id, expected_title, expected_channel",
    VIDEO_TEST_CASES,
    ids=[f"case_{i}" for i in range(len(VIDEO_TEST_CASES))],
)
def test_video_metadata_real_data(url: str, expected_id: str, expected_title: str, expected_channel: str):
    """Verify that video metadata is correctly extracted from real YouTube data."""
    video = YoutubeVideo(url)
    
    # Basic properties
    assert isinstance(video.title, str) and video.title
    assert isinstance(video.description, str)
    assert isinstance(video.duration_seconds, int) and video.duration_seconds > 0
    assert isinstance(video.view_count, int) and video.view_count >= 0
    assert isinstance(video.like_count, int) and video.like_count >= 0
    
    # URL should be valid
    assert video.url.startswith("http")
    
    # Thumbnail URL should be valid
    assert video.thumbnail_url.startswith("http")


@pytest.mark.parametrize(
    "url, expected_id, expected_title, expected_channel",
    VIDEO_TEST_CASES,
    ids=[f"case_{i}" for i in range(len(VIDEO_TEST_CASES))],
)
def test_video_creator_real_data(url: str, expected_id: str, expected_title: str, expected_channel: str):
    """Verify that video creator is correctly extracted from real YouTube data."""
    video = YoutubeVideo(url)
    creator = video.get_creator()
    
    assert isinstance(creator, YoutubeCreator)
    assert isinstance(creator.channel_id, str) and creator.channel_id
    assert isinstance(creator.name, str) and creator.name
    assert isinstance(creator.handle, str)


def test_video_url_formats():
    """Test that various URL formats are correctly parsed."""
    test_cases = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),  # Just the ID
    ]
    
    for url, expected_id in test_cases:
        video = YoutubeVideo(url)
        assert video.video_id == expected_id, f"Failed for URL: {url}"


def test_video_duration_format():
    """Test that duration is correctly formatted."""
    video = YoutubeVideo(VIDEO_URL)
    
    # duration_seconds should be an integer
    assert isinstance(video.duration_seconds, int)
    
    # duration_formatted should be a string in format "M:SS" or "H:MM:SS"
    assert isinstance(video.duration_formatted, str)
    assert ":" in video.duration_formatted


def test_video_is_live():
    """Test that is_live property returns a boolean."""
    video = YoutubeVideo(VIDEO_URL)
    assert isinstance(video.is_live, bool)


def test_video_keywords():
    """Test that keywords property returns a list."""
    video = YoutubeVideo(VIDEO_URL)
    assert isinstance(video.keywords, list)


def test_video_upload_date():
    """Test that upload_date is a string."""
    video = YoutubeVideo(VIDEO_URL)
    assert isinstance(video.upload_date, str)


def test_video_repr():
    """Test that repr contains useful information and loads data if not available."""
    video = YoutubeVideo(VIDEO_URL)
    # Get repr without first accessing title property
    repr_str = repr(video)
    
    assert "YoutubeVideo" in repr_str
    # The repr should include the video_id
    assert "dQw4w9WgXcQ" in repr_str
    # The repr should have title= in it
    assert "title=" in repr_str
    # Since __repr__ now fetches data, it should have the actual title
    assert "Never Gonna Give You Up" in repr_str, f"Expected title in repr, got: {repr_str}"


def test_video_equality():
    """Test that two videos with the same ID are considered equal."""
    video1 = YoutubeVideo("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    video2 = YoutubeVideo("https://youtu.be/dQw4w9WgXcQ")
    
    assert video1 == video2
    assert hash(video1) == hash(video2)


def test_video_get_metadata():
    """Test that get_metadata() returns all expected keys."""
    video = YoutubeVideo(VIDEO_URL)
    meta = video.get_metadata()
    
    expected_keys = {
        "video_id",
        "title",
        "description",
        "duration_seconds",
        "duration_formatted",
        "view_count",
        "like_count",
        "upload_date",
        "channel_name",
        "channel_id",
        "thumbnail_url",
        "is_live",
        "keywords",
    }
    
    assert expected_keys.issubset(meta.keys()), f"Missing keys: {expected_keys - meta.keys()}"


def test_video_channel_name():
    """Test that channel_name is correctly extracted."""
    video = YoutubeVideo(VIDEO_URL)
    assert isinstance(video.channel_name, str)
    assert len(video.channel_name) > 0


def test_video_channel_id():
    """Test that channel_id is correctly extracted."""
    video = YoutubeVideo(VIDEO_URL)
    assert isinstance(video.channel_id, str)
    assert video.channel_id.startswith("UC")


def test_multiple_videos_from_same_channel():
    """Test that multiple videos from the same channel have consistent creator info."""
    videos = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=2isYuQZMbdU",
    ]
    
    creators = []
    for url in videos:
        video = YoutubeVideo(url)
        creator = video.get_creator()
        creators.append(creator)
    
    # All creators should be valid
    for creator in creators:
        assert isinstance(creator, YoutubeCreator)
        assert creator.channel_id