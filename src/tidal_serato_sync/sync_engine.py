import json
import logging
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional
from .crate_handler import CrateHandler
from .tidal_manager import TidalManager
from .db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SyncEngine:
    """Core logic to synchronize Serato crates and Tidal playlists."""

    def __init__(self, config_path: str = "mirrors.json"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.tidal = TidalManager()
        self.db = DatabaseManager()

    def _load_config(self):
        with open(self.config_path, 'r') as f:
            return json.load(f)

    def run_sync(self, max_bitrate: Optional[int] = None):
        """Executes the synchronization for all active mirrors in the database."""
        if not self.tidal.authenticate():
            logging.error("Failed to authenticate with Tidal.")
            return

        # Get active mirrors from Database
        active_mirrors = self.db.get_mirrors(only_active=True)
        if not active_mirrors:
            logging.info("No active mirrors found in the database. Use 'python src/cli.py add [index]' to activate one.")
            return

        for crate_path, playlist_id, direction, _, playlist_name in active_mirrors:
            # Reformat to match what sync_mirror expects (or update sync_mirror)
            mirror = {
                "crate_path": crate_path,
                "playlist_id": playlist_id,
                "direction": direction,
                "playlist_name": playlist_name or Path(crate_path).stem,
                "max_bitrate": max_bitrate
            }
            self.sync_mirror(mirror)

    def sync_mirror(self, mirror):
        crate_path = mirror.get("crate_path")
        playlist_name = mirror.get("playlist_name")
        logging.info(f"Syncing crate {Path(crate_path).name} <-> Tidal '{playlist_name}'")

        # 1. Read Serato Crate
        handler = CrateHandler(crate_path)
        serato_tracks = handler.get_tracks()
        logging.info(f"Found {len(serato_tracks)} tracks in Serato.")

        # 2. Ensure Tidal Playlist exists
        playlist_id = mirror.get("playlist_id")
        
        if not playlist_id:
            logging.info(f"Playlist ID not found in mapping. Creating one...")
            # Detect base folder from settings
            folder_name = self.config.get("settings", {}).get("tidal_base_folder")
            
            # We'll create it if it doesn't exist
            playlist = self.tidal.create_playlist(playlist_name, folder_name=folder_name)
            if playlist:
                playlist_id = playlist.id
                # Update DB with the new playlist ID
                self.db.add_mirror(crate_path, playlist_id)
            else:
                logging.error(f"Could not create/find playlist {playlist_name}")
                return

        # 3. Synchronize Serato -> Tidal
        found_on_tidal = []
        max_bitrate = mirror.get("max_bitrate")

        for track_data in serato_tracks:
            local_path = track_data['local_path']
            # Normalize path for DB (Serato uses leading / often, but let's be consistent)
            db_path = local_path.lstrip('/')
            
            # Check DB cache
            track_info = self.db.get_track_info(db_path)
            tidal_id = track_info['tidal_id'] if track_info else None
            bitrate = track_info['bitrate'] if track_info else None
            
            # Check file existence and get bitrate if missing
            full_path = Path("/" + local_path) if not local_path.startswith("/") else Path(local_path)
            
            if full_path.exists():
                if bitrate is None:
                    bitrate = self.extract_bitrate(full_path)
                    if bitrate:
                        # Update DB with bitrate even if no tidal_id yet
                        self.db.upsert_track(db_path, tidal_id, bitrate=bitrate)
            
            # Bitrate Filter
            if max_bitrate and bitrate and bitrate > max_bitrate:
                logging.info(f"Skipping track {full_path.name} (bitrate {bitrate}k > {max_bitrate}k)")
                continue

            if not tidal_id:
                # Need to search and map
                # Extract artist/title from filename for now (simplified)
                filename = full_path.name
                if " - " in filename:
                    parts = filename.split(" - ", 1)
                    artist = parts[0].split(". ", 1)[-1] if ". " in parts[0] else parts[0]
                    title = parts[1].rsplit(".", 1)[0]
                else:
                    artist = ""
                    title = filename.rsplit(".", 1)[0]
                
                logging.info(f"Searching Tidal for: {title} by {artist}")
                t_track = self.tidal.search_track(title, artist)
                if t_track:
                    tidal_id = t_track.id
                    self.db.upsert_track(db_path, tidal_id, bitrate=bitrate)
                    logging.info(f"Mapped: {db_path} -> {tidal_id} ({bitrate}k)")
                else:
                    logging.warning(f"Could not find on Tidal: {artist} - {title}")
            
            if tidal_id:
                found_on_tidal.append(tidal_id)
                
                # Check if local file exists. If not, prepare for restoration.
                if not full_path.exists():
                    logging.warning(f"File missing at: {full_path}. Marking as pending_download.")
                    self.db.update_track_status(db_path, 'pending_download')
                    try:
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        logging.error(f"Could not create directory {full_path.parent}: {e}")
                else:
                    self.db.update_track_status(db_path, 'synced')

        # Update playlist with all found tracks
        if found_on_tidal:
            logging.info(f"Updating Tidal playlist {playlist_id} with {len(found_on_tidal)} tracks.")
            try:
                self.tidal.add_tracks_to_playlist(playlist_id, found_on_tidal)
            except Exception as e:
                if "404" in str(e) or "Not Found" in str(e):
                    logging.warning(f"Playlist {playlist_id} not found on Tidal. Clearing ID and retrying...")
                    # Update DB to clear the stale ID
                    self.db.add_mirror(crate_path, playlist_id=None)
                    # The next sync run will re-create it. We could retry now but for safety let's wait for next run or manual trigger.
                else:
                    logging.error(f"Error updating playlist: {e}")

    def extract_bitrate(self, file_path: Path) -> Optional[int]:
        """Extracts bitrate in kbps using ffprobe."""
        import subprocess
        import json
        try:
            cmd = [
                'ffprobe', 
                '-v', 'quiet', 
                '-print_format', 'json', 
                '-show_format', 
                str(file_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                bitrate = int(data['format'].get('bit_rate', 0)) // 1000
                return bitrate if bitrate > 0 else None
        except Exception as e:
            logging.debug(f"Error extracting bitrate for {file_path.name}: {e}")
        return None

    def get_recovery_commands(self) -> List[str]:
        """Generates a list of shell commands to download missing tracks using tidal-dl-ng."""
        commands = []
        # Use the absolute path to the binary in the musica environment
        td_bin = "/Users/jpardo/.pyenv/versions/3.12.11/envs/musica/bin/tidal-dl-ng"
        
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT local_path, tidal_track_id FROM track_mapping WHERE status = 'pending_download'")
            rows = cursor.fetchall()
            
            for local_path, tidal_id in rows:
                # Use absolute path
                full_path = Path("/" + local_path) if not local_path.startswith("/") else Path(local_path)
                commands.append(f"# Track: {full_path}")
                # Note: tidal-dl-ng doesn't have a direct -o flag for 'dl'. 
                # It uses the global 'download_base_path'.
                commands.append(f"{td_bin} dl \"https://tidal.com/track/{tidal_id}\"")
        
        return commands

    def run_recovery(self, dry_run: bool = False, quality: str = "LOSSLESS"):
        """Executes recovery commands or just prints them if dry_run is True."""
        # Note: Set default dry_run to False as requested by user (execution by default)
        
        # Configure quality in tidal-dl-ng before starting
        td_bin = "/Users/jpardo/.pyenv/versions/3.12.11/envs/musica/bin/tidal-dl-ng"
        if not dry_run:
            import subprocess
            try:
                logging.info(f"Configurando calidad de audio a: {quality}")
                subprocess.run([td_bin, "cfg", "quality_audio", quality], check=True)
            except Exception as e:
                logging.error(f"No se pudo configurar la calidad en tidal-dl-ng: {e}")

        commands = self.get_recovery_commands()
        if not commands:
            logging.info("No hay archivos marcados como faltantes ('pending_download').")
            return

        if dry_run:
            logging.info("MODO DRY-RUN: Se generarían los siguientes comandos:")
            for cmd in commands:
                print(cmd)
            
            # Also generate the script as a fallback/record
            script_path = Path("recover_missing.sh")
            with open(script_path, "w") as f:
                f.write("#!/bin/bash\n")
                f.write("\n".join(commands))
                
            # Make executable
            import os
            os.chmod(script_path, 0o755)
            logging.info(f"Script de respaldo generado en: {script_path}")
        else:
            import subprocess
            logging.info(f"Iniciando descarga de {len(commands)//2} archivos...")
            try:
            try:
                # Disable subfolders globally for this session to ensure flat download in target dir
                subprocess.run([td_bin, "cfg", "album_folder", "false"], check=False)
                subprocess.run([td_bin, "cfg", "artist_folder", "false"], check=False)
                subprocess.run([td_bin, "cfg", "playlist_folder", "false"], check=False)
                
                import os

                for i in range(0, len(commands), 2):
                    comment = commands[i] # # Track: /path/to/file
                    cmd = commands[i+1]    # tidal-dl ...
                    original_path = comment[9:] # Remove "# Track: "
                    target_dir = Path(original_path).parent
                    
                    if not target_dir.exists():
                        target_dir.mkdir(parents=True, exist_ok=True)
                        
                    print(f"\n==================================================")
                    print(f"Recuperando: {Path(original_path).name}")
                    print(f"Destino: {target_dir}")
                    print(f"==================================================")
                    
                    try:
                        # Configure download path for this specific track
                        subprocess.run([td_bin, "cfg", "download_path", str(target_dir)], check=True)
                        
                        # Snapshot files before download
                        files_before = set(os.listdir(target_dir))
                        
                        # Execute download
                        subprocess.run(cmd, shell=True, check=True)
                        
                        # Snapshot files after download
                        files_after = set(os.listdir(target_dir))
                        new_files = files_after - files_before
                        
                        if new_files:
                            # Assuming one file downloaded per command
                            new_filename = new_files.pop()
                            downloaded_full_path = target_dir / new_filename
                            
                            original_filename = Path(original_path).name
                            
                            if new_filename != original_filename:
                                print(f"⚠️  NOMBRE CAMBIADO: {original_filename}")
                                print(f"   -> ACTUAL: {new_filename}")
                            else:
                                print(f"✅ Descargado correctamente con nombre original.")
                                
                            self.db.update_track_status(original_path, 'downloaded', str(downloaded_full_path))
                        else:
                            # No new file found. Potentially skipped because it exists?
                            print("ℹ️  No se detectó un archivo nuevo (¿posiblemente ya existía o nombre idéntico?)")
                            # We mark as downloaded anyway if exit code was 0, but without changing path
                            self.db.update_track_status(original_path, 'downloaded')
                            
                    except subprocess.CalledProcessError as e:
                        logging.error(f"Error al descargar: {e}")
                        self.db.update_track_status(original_path, 'failed')
                    except Exception as e:
                        logging.error(f"Error inesperado: {e}")
                        self.db.update_track_status(original_path, 'failed')
            except KeyboardInterrupt:
                print("\n\nOperación cancelada por el usuario (Ctrl+C). Saliendo...")
                return

if __name__ == "__main__":
    engine = SyncEngine()
    engine.run_sync()
