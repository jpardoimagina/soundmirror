import argparse
import sys
from pathlib import Path
from .csv_handler import CSVHandler
from .tidal_manager import TidalManager


def main():
    parser = argparse.ArgumentParser(description="Create a Tidal playlist from a CSV file.")
    parser.add_argument("csv_path", help="Path to the CSV file containing tracks.")
    parser.add_argument("playlist_name", help="Name of the playlist to create.")
    parser.add_argument("--folder", help="Name of the Tidal folder to place the playlist in.")
    parser.add_argument("--description", help="Description for the playlist.", default="Created via Tidal Playlist Creator")
    
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print(f"Error: CSV file '{csv_path}' not found.")
        sys.exit(1)

    # 1. Parse CSV
    print(f"Reading tracks from {csv_path}...")
    handler = CSVHandler(str(csv_path))
    try:
        tracks_to_find = handler.parse_tracks()
    except Exception as e:
        print(f"Error parsing CSV: {e}")
        sys.exit(1)

    print(f"Found {len(tracks_to_find)} tracks in CSV.")

    # 2. Authenticate with Tidal
    manager = TidalManager()
    if not manager.authenticate():
        print("Error: Could not authenticate with Tidal.")
        sys.exit(1)

    # 3. Search for tracks on Tidal
    print("\nSearching for tracks on Tidal...")
    found_track_ids = []
    for track_info in tracks_to_find:
        track_name = track_info['track_name']
        artist_name = track_info['artist_name']
        
        print(f" Searching: {track_name} by {artist_name}...", end="", flush=True)
        track = manager.search_track(track_name, artist_name)
        
        if track:
            print(f" Found! ({track.name} by {track.artist.name})")
            found_track_ids.append(track.id)
        else:
            print(" Not found.")

    if not found_track_ids:
        print("\nNo tracks were found on Tidal. Playlist creation cancelled.")
        sys.exit(0)

    # 4. Create Playlist and Add Tracks
    print(f"\nCreating playlist '{args.playlist_name}'...")
    playlist = manager.create_playlist(args.playlist_name, args.description, folder_name=args.folder)
    
    if playlist:
        print(f"Playlist created successfully (ID: {playlist.id}).")
        print(f"Adding {len(found_track_ids)} tracks to the playlist...")
        manager.add_tracks_to_playlist(playlist, found_track_ids)
        print("\nAll done! Enjoy your music.")
    else:
        print("\nFailed to create playlist.")


if __name__ == "__main__":
    main()
