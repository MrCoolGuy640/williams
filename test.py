import pytest

from williams.apis.youtube import YoutubeCreator


# Example YouTube channel URL (Pop Music)
#CHANNEL_URL = "https://www.youtube.com/channel/UC-9-kyTW8ZkZNDHQJ6FgpwQ"
HANDLE_URL = "https://www.youtube.com/@nathandoancomedy"
ID_URL = "https://www.youtube.com/channel/UCX6OQ3DkcsbYNE6H8uQQuVA"

creator = YoutubeCreator(HANDLE_URL)
print(creator.name)
print(creator.channel_id)
print(creator.get_handle_url())
print(creator.get_id_url())


# def test_creator_basic_properties():
#     creator = YoutubeCreator(CHANNEL_URL)
#     # Basic string properties should be non-empty
#     assert creator.name
#     assert creator.channel_id
#     print(creator.url)
#     assert creator.url == CHANNEL_URL
#     # Optional fields may be None, but should be of expected type when present
#     assert isinstance(creator.subscriber_count_text, str)
#     # Get metadata returns a dict
#     meta = creator.get_metadata()
#     assert isinstance(meta, dict)
#     # Ensure uploads playlist can be retrieved
#     playlist = creator.get_uploads_playlist()
#     assert playlist is not None
#     assert hasattr(playlist, "title")


# def test_creator_get_handle_url():
#     """Test that get_handle_url returns a valid URL."""
#     creator = YoutubeCreator(CHANNEL_URL)
#     handle_url = creator.get_handle_url()
    
#     # Should be a non-empty string
#     assert isinstance(handle_url, str) and handle_url
#     # Should start with https://www.youtube.com/
#     assert handle_url.startswith("https://www.youtube.com/")
#     # Should contain either @handle or /channel/UC...
#     assert "@" in handle_url or "/channel/UC" in handle_url


# def test_creator_get_channelid_url():
#     """Test that get_channelid_url returns a valid channel ID URL."""
#     creator = YoutubeCreator(CHANNEL_URL)
#     channelid_url = creator.get_channelid_url()
    
#     # Should be a non-empty string
#     assert isinstance(channelid_url, str) and channelid_url
#     # Should start with https://www.youtube.com/
#     assert channelid_url.startswith("https://www.youtube.com/")
#     # Should contain /channel/UC... if channel ID is available
#     if creator.channel_id:
#         assert "/channel/UC" in channelid_url


# def test_creator_url_vs_handle_vs_channelid():
#     """Test the different URL methods return appropriate formats."""
#     creator = YoutubeCreator(CHANNEL_URL)
    
#     # All URL methods should return strings
#     assert isinstance(creator.url, str)
#     assert isinstance(creator.get_handle_url(), str)
#     assert isinstance(creator.get_channelid_url(), str)
    
#     # All should be valid YouTube URLs
#     assert creator.url.startswith("https://www.youtube.com/")
#     assert creator.get_handle_url().startswith("https://www.youtube.com/")
#     assert creator.get_channelid_url().startswith("https://www.youtube.com/")