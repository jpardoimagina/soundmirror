"""
Tidal-Serato Sync: Bidirectional synchronization between Serato crates and Tidal playlists.

This package provides tools to:
- Sync Serato crates to Tidal playlists
- Recover missing local files by downloading from Tidal
- Filter tracks by bitrate quality
- Manage playlist folders and organization
"""

__version__ = "1.0.0"
__author__ = "Antigravity"

from .cli import main
from .sync_engine import SyncEngine
from .db_manager import DatabaseManager
from .tidal_manager import TidalManager
from .crate_handler import CrateHandler

__all__ = [
    "main",
    "SyncEngine",
    "DatabaseManager",
    "TidalManager",
    "CrateHandler",
]
