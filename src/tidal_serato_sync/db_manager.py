import sqlite3
from pathlib import Path
from typing import Optional, Dict


class DatabaseManager:
    """Manages the SQLite database for mapping local files to Tidal tracks."""

    def __init__(self, db_path: str = "sync_map.db"):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self):
        """Initializes the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Table for track mapping
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS track_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    local_path TEXT UNIQUE,
                    tidal_track_id TEXT,
                    isrc TEXT,
                    bitrate INTEGER,
                    last_sync TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'synced',
                    downloaded_path TEXT
                )
            """)
            # Table for mirrored crates
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mirror_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    crate_path TEXT UNIQUE,
                    crate_name TEXT,
                    tidal_playlist_id TEXT,
                    sync_direction TEXT DEFAULT 'bidirectional',
                    is_active INTEGER DEFAULT 0
                )
            """)
            
            # Table for tracking Tidal-originated tracks pending Crate assignment
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_crate_additions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tidal_id TEXT,
                    crate_path TEXT,
                    UNIQUE(tidal_id, crate_path)
                )
            """)
            
            # Migration check: ensure crate_path exists in mirror_config
            cursor.execute("PRAGMA table_info(mirror_config)")
            columns = [info[1] for info in cursor.fetchall()]
            if 'crate_path' not in columns:
                # If it's the old schema, it's easier to recreate it since crate_path is new and UNIQUE
                cursor.execute("DROP TABLE mirror_config")
                cursor.execute("""
                    CREATE TABLE mirror_config (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        crate_path TEXT UNIQUE,
                        crate_name TEXT,
                        tidal_playlist_id TEXT,
                        sync_direction TEXT DEFAULT 'bidirectional',
                        is_active INTEGER DEFAULT 0
                    )
                """)
            # Migration check: ensure bitrate column exists
            cursor.execute("PRAGMA table_info(track_mapping)")
            cols = [info[1] for info in cursor.fetchall()]
            if 'bitrate' not in cols:
                cursor.execute("ALTER TABLE track_mapping ADD COLUMN bitrate INTEGER")
            
            # Migration check: ensure downloaded_path column exists
            if 'downloaded_path' not in cols:
                cursor.execute("ALTER TABLE track_mapping ADD COLUMN downloaded_path TEXT")
            
            # Migration check: ensure display_name column exists
            if 'display_name' not in cols:
                cursor.execute("ALTER TABLE track_mapping ADD COLUMN display_name TEXT")
            
            # Clean up existing crate_name extensions if any
            cursor.execute("UPDATE mirror_config SET crate_name = REPLACE(crate_name, '.crate', '') WHERE crate_name LIKE '%.crate'")
            conn.commit()

    def upsert_track(self, local_path: str, tidal_id: str, isrc: Optional[str] = None, bitrate: Optional[int] = None, display_name: Optional[str] = None):
        """Adds or updates a track mapping."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO track_mapping (local_path, tidal_track_id, isrc, bitrate, last_sync, display_name)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(local_path) DO UPDATE SET
                    tidal_track_id = excluded.tidal_track_id,
                    isrc = excluded.isrc,
                    bitrate = COALESCE(excluded.bitrate, track_mapping.bitrate),
                    display_name = COALESCE(excluded.display_name, track_mapping.display_name),
                    last_sync = CURRENT_TIMESTAMP
            """, (local_path, tidal_id, isrc, bitrate, display_name))
            conn.commit()

    def update_track_status(self, local_path: str, status: str, downloaded_path: Optional[str] = None):
        """Updates the status and optional downloaded path of a track."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if downloaded_path:
                cursor.execute("UPDATE track_mapping SET status = ?, downloaded_path = ? WHERE local_path = ?", (status, downloaded_path, local_path))
            else:
                cursor.execute("UPDATE track_mapping SET status = ? WHERE local_path = ?", (status, local_path))
            conn.commit()

    def get_track_info(self, local_path: str) -> Optional[Dict]:
        """Gets the Tidal ID and bitrate for a given local path."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT tidal_track_id, bitrate FROM track_mapping WHERE local_path = ?", (local_path,))
            result = cursor.fetchone()
            if result:
                return {'tidal_id': result[0], 'bitrate': result[1]}
            return None

    def get_tidal_id(self, local_path: str) -> Optional[str]:
        """Gets the Tidal ID for a given local path."""
        info = self.get_track_info(local_path)
        return info['tidal_id'] if info else None

    def bulk_add_discovered_crates(self, crates):
        """Adds multiple crates as discovered/inactive."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for crate_path in crates:
                cursor.execute("""
                    INSERT OR IGNORE INTO mirror_config (crate_path, crate_name, is_active)
                    VALUES (?, ?, 0)
                """, (str(crate_path), crate_path.stem))
            conn.commit()

    def add_mirror(self, crate_path: str, playlist_id: Optional[str], direction: str = "bidirectional", is_active: int = 1):
        """Configures a mirror between a crate and a playlist."""
        crate_name = Path(crate_path).stem
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO mirror_config (crate_path, crate_name, tidal_playlist_id, sync_direction, is_active)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(crate_path) DO UPDATE SET
                    tidal_playlist_id = excluded.tidal_playlist_id,
                    sync_direction = excluded.sync_direction,
                    is_active = excluded.is_active
            """, (crate_path, crate_name, playlist_id, direction, is_active))
            conn.commit()

    def remove_mirror(self, crate_path: str):
        """Removes a mirror from the database when the crate no longer exists."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM mirror_config WHERE crate_path = ?", (str(crate_path),))
            conn.commit()

    def get_mirrors(self, only_active: bool = False):
        """Returns all configured mirrors."""
        query = "SELECT crate_path, tidal_playlist_id, sync_direction, is_active, crate_name FROM mirror_config"
        if only_active:
            query += " WHERE is_active = 1"
            
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            return cursor.fetchall()
            
    def add_pending_crate_addition(self, tidal_id: str, crate_path: str):
        """Records a new Tidal track that needs to be added to a Crate once downloaded."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO pending_crate_additions (tidal_id, crate_path)
                VALUES (?, ?)
            """, (tidal_id, str(crate_path)))
            conn.commit()
            
    def get_pending_crate_additions(self, tidal_id: str) -> list[str]:
        """Returns the list of crate paths that are waiting for this Tidal track."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT crate_path FROM pending_crate_additions WHERE tidal_id = ?", (tidal_id,))
            return [row[0] for row in cursor.fetchall()]
            
    def remove_pending_crate_additions(self, tidal_id: str):
        """Clears all pending crate additions for a specific Tidal track once applied."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pending_crate_additions WHERE tidal_id = ?", (tidal_id,))
            conn.commit()

    def clear_all_track_mappings(self):
        """Removes all track mappings and pending cleanup records from the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM track_mapping")
            cursor.execute("DELETE FROM pending_crate_additions")
            conn.commit()
