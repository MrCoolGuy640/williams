import pytest

from williams.apis.youtube import YoutubeCreator

HANDLE_URL = "https://www.youtube.com/@nathandoancomedy"
ID_URL = "https://www.youtube.com/channel/UCdyMFblTjr-C2N-T5TGftQQ"

EXPECTED_HANDLE = "nathandoancomedy"
EXPECTED_ID = "UCdyMFblTjr-C2N-T5TGftQQ"
EXPECTED_NAME = "Nathan Doan Comedy"

@pytest.mark.parametrize("channel_url", [ HANDLE_URL, ID_URL ])
def test_basic_creator_properties(channel_url: str):
    creator = YoutubeCreator(channel_url)

    assert creator.channel_id == EXPECTED_ID

    assert creator.get_handle_url() == HANDLE_URL
    assert creator.get_id_url() == ID_URL

    assert creator.name == EXPECTED_NAME



# @pytest.mark.parametrize("channel_url", [HANDLE_URL, ID_URL])
# def test_metadata(channel_url: str):
#     creator = YoutubeCreator(channel_url)
#     meta = creator.get_metadata()

#     assert isinstance(meta, dict)

#     required_keys = {
#         "channel_id",
#         "handle",
#         "handle_url",
#         "id_url",
#         "name",
#         "description",
#         "subscriber_text",
#         "avatar_url",
#         "banner_url",
#         "uploads_playlist_id",
#     }

#     assert required_keys.issubset(meta.keys())

#     # ensure all required fields are non-empty
#     for key in required_keys:
#         assert meta[key] is not None, f"{key} is None"
#         assert meta[key] != "", f"{key} is empty string"
@pytest.mark.parametrize("channel_url", [HANDLE_URL, ID_URL])
def test_metadata(channel_url: str):
    creator = YoutubeCreator(channel_url)
    meta = creator.get_metadata()

    assert isinstance(meta, dict)

    required_keys = {
        "channel_id",
        "handle",
        "handle_url",
        "id_url",
        "name",
        "description",
        "subscriber_text",
        "avatar_url",
        "banner_url",
        "uploads_playlist_id",
    }

    assert required_keys.issubset(meta.keys())

    failures = []

    for key in required_keys:
        value = meta.get(key)

        if value is None:
            failures.append(f"{key} is None")
        elif value == "":
            failures.append(f"{key} is empty string")

    assert not failures, "Metadata validation failed:\n" + "\n".join(failures)


def test_subscriber_text_is_safe_string():
    creator = YoutubeCreator(HANDLE_URL)

    assert isinstance(creator.subscriber_count_text, str)

    # must not crash even if empty or weird format
    text = creator.subscriber_count_text

    if text:
        # it should contain a number
        assert any(c.isdigit() for c in text)



def test_creator_videoslist_behaviour():
    creator = YoutubeCreator(HANDLE_URL)

    playlist = creator.get_uploads_playlist()
    assert playlist is not None
    assert hasattr(playlist, "title")


def test_creator_handle_resolution():
    """Test that the creator is correctly resolved from different input formats."""
    # Test with handle URL
    creator1 = YoutubeCreator("https://www.youtube.com/@MrBeast")
    assert creator1.handle == "MrBeast"
    
    # Test with channel ID URL
    creator2 = YoutubeCreator("https://www.youtube.com/channel/UCX6OQ3DkcsbYNE6H8uQQuVA")
    assert creator2.handle == "MrBeast"
    
    # Test with @Handle
    creator3 = YoutubeCreator("@MrBeast")
    assert creator3.handle == "MrBeast"
    
    # Test with channel ID
    creator4 = YoutubeCreator("UCX6OQ3DkcsbYNE6H8uQQuVA")
    assert creator4.handle == "MrBeast"


# ============================================================================
# Comprehensive tests with real data
# ============================================================================

# --- Test data: (URL, expected_channel_id, expected_handle, expected_name) ---
CHANNEL_TEST_CASES = [
    # Handle-based URL
    (
        "https://www.youtube.com/@nathandoancomedy",
        "UCdyMFblTjr-C2N-T5TGftQQ",
        "nathandoancomedy",
        "Nathan Doan Comedy",
    ),
    # Channel ID URL
    (
        "https://www.youtube.com/channel/UCdyMFblTjr-C2N-T5TGftQQ",
        "UCdyMFblTjr-C2N-T5TGftQQ",
        "nathandoancomedy",
        "Nathan Doan Comedy",
    ),
    # Large channel: MrBeast
    (
        "https://www.youtube.com/@MrBeast",
        "UCX6OQ3DkcsbYNE6H8uQQuVA",
        "MrBeast",
        "MrBeast",
    ),
    # Large channel via ID URL
    (
        "https://www.youtube.com/channel/UCX6OQ3DkcsbYNE6H8uQQuVA",
        "UCX6OQ3DkcsbYNE6H8uQQuVA",
        "MrBeast",
        "MrBeast",
    ),
    # Linus Tech Tips
    (
        "https://www.youtube.com/@LinusTechTips",
        "UCXuqSBlHAE6Xw-yeJA0Tunw",
        "LinusTechTips",
        "Linus Tech Tips",
    ),
    # Marques Brownlee
    (
        "https://www.youtube.com/@mkbhd",
        "UCBJycsmduvYEL83R_U4JriQ",
        "mkbhd",
        "Marques Brownlee",
    ),
    # Shorts channel
    (
        "https://www.youtube.com/@PewDiePie",
        "UC-lHJZR3Gqxm24_Vd_AJ5Yw",
        "PewDiePie",
        "PewDiePie",
    ),
]


@pytest.mark.parametrize(
    "url, expected_id, expected_handle, expected_name",
    CHANNEL_TEST_CASES,
    ids=[f"case_{i}" for i in range(len(CHANNEL_TEST_CASES))],
)
def test_channel_identity_real_data(url: str, expected_id: str, expected_handle: str, expected_name: str):
    """Verify that channel identity (ID, handle, name) is correctly extracted from real YouTube data."""
    creator = YoutubeCreator(url)
    assert creator.channel_id == expected_id, f"Channel ID mismatch for {url}"
    assert creator.handle == expected_handle, f"Handle mismatch for {url}"
    assert creator.name == expected_name, f"Name mismatch for {url}"


@pytest.mark.parametrize(
    "url, expected_id, expected_handle, expected_name",
    CHANNEL_TEST_CASES,
    ids=[f"case_{i}" for i in range(len(CHANNEL_TEST_CASES))],
)
def test_channel_urls_real_data(url: str, expected_id: str, expected_handle: str, expected_name: str):
    """Verify that handle_url and id_url are correctly generated."""
    creator = YoutubeCreator(url)
    handle_url = creator.get_handle_url()
    id_url = creator.get_id_url()
    
    assert handle_url == f"https://www.youtube.com/@{expected_handle}"
    assert id_url == f"https://www.youtube.com/channel/{expected_id}"


@pytest.mark.parametrize(
    "url, expected_id, expected_handle, expected_name",
    CHANNEL_TEST_CASES,
    ids=[f"case_{i}" for i in range(len(CHANNEL_TEST_CASES))],
)
def test_channel_metadata_non_empty_real_data(url: str, expected_id: str, expected_handle: str, expected_name: str):
    """Verify that all metadata fields are non-empty for real channels."""
    creator = YoutubeCreator(url)
    meta = creator.get_metadata()
    
    assert isinstance(meta, dict)
    assert meta["channel_id"] == expected_id
    assert meta["handle"] == expected_handle
    assert meta["name"] == expected_name
    assert meta["handle_url"] == f"https://www.youtube.com/@{expected_handle}"
    assert meta["id_url"] == f"https://www.youtube.com/channel/{expected_id}"
    assert meta["uploads_playlist_id"] == f"UU{expected_id[2:]}"
    
    # These should be non-empty for real channels
    assert meta["description"] is not None, f"description is None for {url}"
    assert meta["subscriber_text"] is not None, f"subscriber_text is None for {url}"
    assert meta["avatar_url"] is not None, f"avatar_url is None for {url}"
    assert meta["banner_url"] is not None, f"banner_url is None for {url}"
    
    # Check that URLs are valid
    assert meta["avatar_url"].startswith("http"), f"avatar_url is not a valid URL for {url}"
    assert meta["banner_url"].startswith("http"), f"banner_url is not a valid URL for {url}"


@pytest.mark.parametrize(
    "url, expected_id, expected_handle, expected_name",
    CHANNEL_TEST_CASES,
    ids=[f"case_{i}" for i in range(len(CHANNEL_TEST_CASES))],
)
def test_channel_subscriber_text_format_real_data(url: str, expected_id: str, expected_handle: str, expected_name: str):
    """Verify that subscriber text contains a number and has expected format."""
    creator = YoutubeCreator(url)
    sub_text = creator.subscriber_count_text
    
    assert isinstance(sub_text, str)
    assert len(sub_text) > 0, f"subscriber_text is empty for {url}"
    
    # Should contain a number
    assert any(c.isdigit() for c in sub_text), f"subscriber_text has no digits for {url}: {sub_text}"
    
    # Should contain "subscriber" (case-insensitive)
    assert "subscriber" in sub_text.lower(), f"subscriber_text doesn't contain 'subscriber' for {url}: {sub_text}"


@pytest.mark.parametrize(
    "url, expected_id, expected_handle, expected_name",
    CHANNEL_TEST_CASES,
    ids=[f"case_{i}" for i in range(len(CHANNEL_TEST_CASES))],
)
def test_channel_uploads_playlist_real_data(url: str, expected_id: str, expected_handle: str, expected_name: str):
    """Verify that uploads playlist ID is correctly derived and accessible."""
    creator = YoutubeCreator(url)
    uploads_id = creator.uploads_playlist_id
    
    assert uploads_id is not None
    assert uploads_id.startswith("UU")
    assert uploads_id == f"UU{expected_id[2:]}"
    
    # Verify we can get the playlist object
    playlist = creator.get_uploads_playlist()
    assert playlist is not None
    assert hasattr(playlist, "title")


def test_channel_equality_and_hash():
    """Test that two creators with the same channel ID are considered equal."""
    creator1 = YoutubeCreator(HANDLE_URL)
    creator2 = YoutubeCreator(ID_URL)
    
    assert creator1 == creator2
    assert hash(creator1) == hash(creator2)


def test_channel_repr():
    """Test that repr contains useful information."""
    creator = YoutubeCreator(HANDLE_URL)
    repr_str = repr(creator)
    
    assert "YoutubeCreator" in repr_str
    assert EXPECTED_HANDLE in repr_str
    assert EXPECTED_NAME in repr_str


def test_channel_reload():
    """Test that reload() clears cache and re-fetches data."""
    creator = YoutubeCreator(HANDLE_URL)
    
    # Access data to populate cache
    _ = creator.name
    
    # Reload should not raise
    result = creator.reload()
    assert result is creator
    
    # Data should still be accessible
    assert creator.name == EXPECTED_NAME
    assert creator.channel_id == EXPECTED_ID


@pytest.mark.parametrize(
    "url, expected_id, expected_handle, expected_name",
    CHANNEL_TEST_CASES,
    ids=[f"case_{i}" for i in range(len(CHANNEL_TEST_CASES))],
)
def test_channel_metadata_dict_keys_real_data(url: str, expected_id: str, expected_handle: str, expected_name: str):
    """Verify that get_metadata() returns all expected keys."""
    creator = YoutubeCreator(url)
    meta = creator.get_metadata()
    
    expected_keys = {
        "channel_id",
        "handle",
        "handle_url",
        "id_url",
        "name",
        "description",
        "subscriber_text",
        "avatar_url",
        "banner_url",
        "uploads_playlist_id",
    }
    
    assert expected_keys.issubset(meta.keys()), f"Missing keys: {expected_keys - meta.keys()}"


def test_multiple_channels_iteration():
    """Test iterating over videos from multiple channels."""
    channels = [
        ("https://www.youtube.com/@nathandoancomedy", "UCdyMFblTjr-C2N-T5TGftQQ"),
        ("https://www.youtube.com/@MrBeast", "UCX6OQ3DkcsbYNE6H8uQQuVA"),
    ]
    
    for url, expected_id in channels:
        creator = YoutubeCreator(url)
        assert creator.channel_id == expected_id
        
        # Get uploads playlist
        playlist = creator.get_uploads_playlist()
        assert playlist is not None


def test_channel_with_special_characters_in_description():
    """Test that channels with special characters in description are handled."""
    creator = YoutubeCreator(HANDLE_URL)
    description = creator.description
    
    assert isinstance(description, str)
    # Description should be accessible without errors
    # (actual content depends on the channel)