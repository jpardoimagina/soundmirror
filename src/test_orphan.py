from tidal_serato_sync.sync_engine import SyncEngine
from pathlib import Path
engine = SyncEngine()
engine._create_orphan_crate("test_orphan_v2", ["Users/jpardo/Music/TestTrack.mp3"], Path("/Users/jpardo/Music/_Serato_/Subcrates"))
print("Test complete.")
