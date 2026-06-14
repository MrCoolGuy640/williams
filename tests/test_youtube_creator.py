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
        # optional sanity check (non-fatal format check)
        assert any(c.isdigit() for c in text)



def test_creator_videoslist_behaviour():
    creator = YoutubeCreator(HANDLE_URL)

    playlist = creator.get_uploads_playlist()
    assert playlist is not None
    assert hasattr(playlist, "title")


def test_creator_handle_resolution():
    """Test that handle is correctly resolved from different input formats."""
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