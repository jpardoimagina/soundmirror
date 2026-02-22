import tidalapi
import json
import os
from pathlib import Path
from typing import List, Optional


class TidalManager:
    """Manages interactions with the Tidal API."""

    TOKEN_FILE = Path(".tidal_token.json")

    def __init__(self):
        """Initialize the TidalManager."""
        self.session = tidalapi.Session()
        self.user = None

    def authenticate(self) -> bool:
        """
        Authenticates the user with Tidal using Device Login flow.
        Attempts to load existing tokens first.

        :return: True if authentication is successful, False otherwise.
        """
        if self._load_token():
            if self.session.check_login():
                self.user = self.session.user
                print("Successfully authenticated using saved tokens.")
                return True
            else:
                print("Saved tokens are invalid or expired. Re-authenticating...")

        # Device Login Flow
        login, future = self.session.login_oauth()
        print(f"Please visit: {login.verification_uri_complete}")
        print(f"And enter the code if prompted: {login.user_code}")
        
        # Wait for user to complete login
        future.result()

        if self.session.check_login():
            self.user = self.session.user
            self._save_token()
            print("Authentication successful!")
            return True
        
        return False

    def _save_token(self):
        """Saves session tokens to a file."""
        data = {
            'token_type': self.session.token_type,
            'access_token': self.session.access_token,
            'refresh_token': self.session.refresh_token,
            'expiry_time': self.session.expiry_time.isoformat() if self.session.expiry_time else None
        }
        with open(self.TOKEN_FILE, 'w') as f:
            json.dump(data, f)

    def _load_token(self) -> bool:
        """Loads session tokens from a file if they exist."""
        if not self.TOKEN_FILE.exists():
            return False
        
        try:
            with open(self.TOKEN_FILE, 'r') as f:
                data = json.load(f)
            
            # Note: tidalapi Session.load_oauth_session might be available in some versions
            # but we can also set them manually or use the appropriate library method.
            # For simplicity and compatibility with various versions of the lib:
            self.session.load_oauth_session(
                data['token_type'],
                data['access_token'],
                data['refresh_token'],
                # expiry_time is not always needed for load
            )
            return True
        except Exception:
            return False

    def search_track(self, track_name: str, artist_name: str) -> Optional[tidalapi.Track]:
        """
        Searches for a track by name and artist.

        :param track_name: Name of the track.
        :param artist_name: Name of the artist.
        :return: The first matching Track object or None.
        """
        query = f"{track_name} {artist_name}"
        search_result = self.session.search(query, models=[tidalapi.Track], limit=10)
        
        # Try to find a good match in the results
        for track in search_result.get('tracks', []):
            # Simple check: does the artist match roughly?
            if artist_name.lower() in track.artist.name.lower() or \
               track.artist.name.lower() in artist_name.lower():
                return track
        
        # Fallback to first result if any
        if search_result.get('tracks'):
            return search_result['tracks'][0]
            
        return None

    def create_folder(self, folder_name: str) -> Optional[str]:
        """
        Creates a new folder in the user's Tidal account.
        """
        if not self.user:
            return None
        try:
            # Note: tidalapi 0.7+ might have user.create_folder
            # If not, it might be session.create_folder
            folder = self.user.create_folder(folder_name)
            return folder.id
        except Exception as e:
            print(f"Error creating Tidal folder '{folder_name}': {e}")
            return None

    def get_folder_by_name(self, folder_name: str) -> Optional[str]:
        """
        Searches for a folder by name among the user's folders.
        """
        if not self.user:
            return None
        
        try:
            # Get user's folders/items from root
            root_folder = self.session.folder()
            for item in root_folder.items():
                if isinstance(item, tidalapi.playlist.Folder) and item.name.lower() == folder_name.lower():
                    return item.id
            return None
        except Exception as e:
            print(f"Error searching for folder '{folder_name}': {e}")
            return None

    def move_playlist_to_folder(self, playlist_id: str, folder_id: str) -> bool:
        """
        Moves a playlist into a folder.
        """
        try:
            folder = self.session.folder(folder_id)
            # Try TRN format first
            playlist_trn = f"trn:tidal:playlist:{playlist_id}"
            try:
                folder.add_items([playlist_trn])
                return True
            except Exception as e:
                print(f"TRN move failed: {e}. Trying direct ID...")
                # Try just the ID as a fallback
                folder.add_items([playlist_id])
                return True
        except Exception as e:
            print(f"Error moving playlist {playlist_id} to folder {folder_id}: {e}")
            return False

    def create_playlist(self, title: str, description: str = "", folder_name: str = None) -> Optional[tidalapi.Playlist]:
        """
        Creates a new playlist and optionally moves it to a folder.

        :param title: Title of the playlist.
        :param description: Description of the playlist.
        :param folder_name: Optional name of the folder to put the playlist in.
        :return: The created Playlist object or None.
        """
        if not self.user:
            print("Error: User not authenticated.")
            return None
        
        try:
            playlist = self.user.create_playlist(title, description)
            if playlist and folder_name:
                print(f"Searching for folder '{folder_name}'...")
                folder_id = self.get_folder_by_name(folder_name)
                if not folder_id:
                    print(f"Folder '{folder_name}' not found. Creating it...")
                    folder_id = self.create_folder(folder_name)
                
                if folder_id:
                    print(f"Moving playlist to folder '{folder_name}' (ID: {folder_id})...")
                    if self.move_playlist_to_folder(playlist.id, folder_id):
                        print("Successfully moved to folder.")
                    else:
                        print(f"Warning: Could not move playlist to folder '{folder_name}'.")
                else:
                    print(f"Warning: Could not find or create folder '{folder_name}'.")
            return playlist
        except Exception as e:
            print(f"Error creating playlist: {e}")
            return None

    def get_playlist(self, playlist_id: str) -> Optional[tidalapi.Playlist]:
        """Gets a playlist object by ID."""
        try:
            return self.session.playlist(playlist_id)
        except Exception:
            return None

    def get_playlist_tracks(self, playlist_id: str) -> List[tidalapi.Track]:
        """Gets all tracks from a playlist."""
        try:
            playlist = self.get_playlist(playlist_id)
            if playlist:
                return playlist.tracks()
            return []
        except Exception as e:
            print(f"Error getting tracks for playlist {playlist_id}: {e}")
            return []

    def add_tracks_to_playlist(self, playlist_id: str, track_ids: List[str]):
        """
        Adds tracks to a playlist by ID.

        :param playlist_id: The ID of the playlist.
        :param track_ids: List of track IDs to add.
        """
        try:
            playlist = self.get_playlist(playlist_id)
            if playlist:
                playlist.add(track_ids)
                print(f"Added {len(track_ids)} tracks to playlist '{playlist.name}'.")
            else:
                print(f"Error: Playlist {playlist_id} not found.")
        except Exception as e:
            print(f"Error adding tracks to playlist: {e}")


if __name__ == "__main__":
    # Quick test (requires manual authentication)
    manager = TidalManager()
    if manager.authenticate():
        track = manager.search_track("Blinding Lights", "The Weeknd")
        if track:
            print(f"Found track: {track.name} by {track.artist.name} (ID: {track.id})")
        else:
            print("Track not found.")
