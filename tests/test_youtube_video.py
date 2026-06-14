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
