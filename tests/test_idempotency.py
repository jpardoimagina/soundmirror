import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from tidal_serato_sync.crate_handler import CrateHandler
from tidal_serato_sync.tidal_manager import TidalManager
from tidal_serato_sync.sync_engine import SyncEngine

class TestIdempotency(unittest.TestCase):
    def setUp(self):
        self.test_crate = Path("/tmp/test_idempotency.crate")
        if self.test_crate.exists():
            self.test_crate.unlink()

    def tearDown(self):
        if self.test_crate.exists():
            self.test_crate.unlink()

    def test_crate_handler_idempotency(self):
        handler = CrateHandler(str(self.test_crate))
        track_path = "Users/test/Music/track1.mp3"
        
        # First addition
        self.assertTrue(handler.add_track_to_crate(track_path))
        tracks = handler.get_tracks()
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]['local_path'], track_path)
        
        # Second addition (should be ignored)
        self.assertFalse(handler.add_track_to_crate(track_path))
        tracks = handler.get_tracks()
        self.assertEqual(len(tracks), 1)

    @patch('tidalapi.Session')
    def test_tidal_manager_idempotency(self, mock_session):
        manager = TidalManager()
        mock_playlist = MagicMock()
        mock_playlist.name = "Test Playlist"
        
        track1 = MagicMock()
        track1.id = "123"
        track1.name = "Track 1"
        
        mock_playlist.tracks.return_value = [track1]
        
        with patch.object(manager, 'get_playlist', return_value=mock_playlist):
            # Try to add existing track
            manager.add_tracks_to_playlist("playlist_id", ["123"])
            mock_playlist.add.assert_not_called()
            
            # Try to add new track
            manager.add_tracks_to_playlist("playlist_id", ["456"])
            mock_playlist.add.assert_called_once_with(["456"])

if __name__ == "__main__":
    unittest.main()
