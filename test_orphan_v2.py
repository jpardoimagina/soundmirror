import sys
from pathlib import Path

# Add src to python path to allow imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from tidal_serato_sync.sync_engine import SyncEngine

engine = SyncEngine()
engine._create_orphan_crate(
    "test_orphan_v2", 
    ["Users/jpardo/Music/TestTrack.mp3"], 
    Path("/Users/jpardo/Desktop") # use a local safe test path for tests
)
print("Test complete.")
