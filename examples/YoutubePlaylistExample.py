from williams.apis.youtube import YoutubePlaylist, YoutubeVideo

# Example public playlist URL (YouTube Music Top 100)
PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj"


def run_manual_test():
    playlist = YoutubePlaylist(PLAYLIST_URL)

    print("Title:", playlist.title, "| type:", type(playlist.title))
    print("Playlist ID:", playlist.playlist_id, "| type:", type(playlist.playlist_id))
    print("URL:", playlist.url)

    count = playlist.video_count
    print("Video Count:", count, "| type:", type(count))

    owner = playlist.owner
    print("Owner:", owner, "| type:", type(owner))
    
    owner_handle = playlist.owner_handle
    print("Owner Handle:", owner_handle, "| type:", type(owner_handle))
    
    owner_id = playlist.owner_id
    print("Owner ID:", owner_id, "| type:", type(owner_id))
    
    views = playlist.views
    print("Views:", views, "| type:", type(views))
    
    print("\n=== FIRST VIDEO ===")
    first_video = playlist.get_video_at_index(0)
    print("First video object:", first_video)
    print("Type:", type(first_video))

    print("\n=== DONE ===")


if __name__ == "__main__":
    run_manual_test()