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

    def run_sync(self, max_bitrate: Optional[int] = None, force_update: bool = False, orphan_crate: Optional[str] = None):
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
                "max_bitrate": max_bitrate,
                "force_update": force_update,
                "orphan_crate": orphan_crate
            }
            try:
                self.sync_mirror(mirror)
            except FileNotFoundError as e:
                logging.warning(f"Crate {crate_path} not found. Removing from local mappings. ({e})")
                self.db.remove_mirror(crate_path)
            except Exception as e:
                logging.error(f"Error syncing {crate_path}: {e}")

    def sync_mirror(self, mirror):
        crate_path = mirror.get("crate_path")
        playlist_name = mirror.get("playlist_name")
        max_bitrate = mirror.get("max_bitrate")
        force_update = mirror.get("force_update", False)
        orphan_crate_name = mirror.get("orphan_crate", None)
        
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

        # Fetch current playlist tracks once for efficiency and idempotency checks
        playlist_tracks = self.tidal.get_playlist_tracks(playlist_id)
        tidal_playlist_ids = {str(t.id) for t in playlist_tracks if hasattr(t, 'id')}

        # 3. Synchronize Serato -> Tidal
        found_on_tidal = []
        orphaned_tracks = []
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
                
                if not t_track:
                    # Retry with cleaned artist/title
                    clean_title = self._clean_search_term(title)
                    clean_artist = self._clean_search_term(artist)
                    if clean_title != title or clean_artist != artist:
                        logging.info(f"Retrying search with cleaned terms: {clean_title} by {clean_artist}")
                        t_track = self.tidal.search_track(clean_title, clean_artist)

                if t_track:
                    tidal_id = str(t_track.id)
                    self.db.upsert_track(db_path, tidal_id, bitrate=bitrate)
                    logging.info(f"\033[92mMapped: {db_path} -> {tidal_id} ({bitrate}k)\033[0m")
                else:
                    logging.warning(f"\033[91mCould not find on Tidal: {artist} - {title}\033[0m")
                    orphaned_tracks.append(db_path)
            
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
                    if force_update:
                        logging.warning(f"Forcing update for existing file: {full_path}. Marking as pending_download.")
                        self.db.update_track_status(db_path, 'pending_download')
                    else:
                        self.db.update_track_status(db_path, 'synced')

        # Update playlist with all found tracks
        if found_on_tidal:
            # Filter matches that already exist in the playlist for logging purposes, 
            # though tidal_manager also handles this.
            ids_to_add = [tid for tid in found_on_tidal if str(tid) not in tidal_playlist_ids]
            
            if ids_to_add:
                logging.info(f"Adding {len(ids_to_add)} new tracks to Tidal playlist {playlist_id}.")
                try:
                    self.tidal.add_tracks_to_playlist(playlist_id, ids_to_add)
                except Exception as e:
                    if "404" in str(e) or "Not Found" in str(e):
                        logging.warning(f"Playlist {playlist_id} not found on Tidal. Clearing ID and retrying...")
                        self.db.add_mirror(crate_path, playlist_id=None)
                    else:
                        logging.error(f"Error updating playlist: {e}")
            else:
                logging.info(f"Tidal playlist {playlist_name} is already up to date.")

        # 4. Synchronize Tidal -> Serato (check for new tracks on Tidal)
        logging.info(f"Checking for new tracks added to Tidal playlist {playlist_name}...")
        new_from_tidal = 0
        
        # We reuse playlist_tracks fetched at the beginning
        
        for pt in playlist_tracks:
            if not hasattr(pt, 'id'): continue
            tidal_id = str(pt.id)
            if tidal_id not in found_on_tidal:
                logging.info(f"Found new track on Tidal: {pt.name} - {pt.artist.name}")
                placeholder_path = f"TIDAL_IMPORT:{tidal_id}"
                
                display_name = f"{pt.artist.name} - {pt.name}"
                self.db.upsert_track(placeholder_path, tidal_id, display_name=display_name)
                self.db.update_track_status(placeholder_path, 'pending_download')
                
                # Register that it needs to be added to THIS crate
                self.db.add_pending_crate_addition(tidal_id, crate_path)
                new_from_tidal += 1
                
        if new_from_tidal > 0:
            logging.info(f"Scheduled {new_from_tidal} new track(s) from Tidal for download.")

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
                '-show_streams',
                str(file_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                bitrate = int(data.get('format', {}).get('bit_rate', 0) or 0) // 1000
                
                if bitrate <= 0:
                    for stream in data.get('streams', []):
                        if stream.get('codec_type') == 'audio':
                            bitrate = int(stream.get('bit_rate', 0) or 0) // 1000
                            if bitrate > 0:
                                break
                                
                if bitrate <= 0 and file_path.suffix.lower() == '.flac':
                    bitrate = 900
                    
                return bitrate if bitrate > 0 else None
        except Exception as e:
            logging.debug(f"Error extracting bitrate for {file_path.name}: {e}")
            
        if file_path.suffix.lower() == '.flac':
            return 900
            
        return None

    def _clean_search_term(self, text: str) -> str:
        """Removes common dirty characters/tags from track or artist names to improve search matches."""
        if not text:
            return text
            
        import re
        # Remove Youtube ID format at the end (e.g. -6kzXyhqtKuE)
        text = re.sub(r'-[a-zA-Z0-9_\-]{11}$', '', text)
        # Remove any bracketed text [like this]
        text = re.sub(r'\[.*?\]', '', text)
        # Remove standalone Out Now!
        text = re.sub(r'(?i)\bout now!?\b', '', text)

        # Remove bitrates e.g. 320Kbps, 192 Kbps, 320Kbs
        text = re.sub(r'\b\d{3}\s*[Kk]bps?\b', '', text, flags=re.IGNORECASE)
        # Remove video/promo tags
        text = re.sub(r'\(?Official(?: Music)? Video\)?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\(?Lyric video\)?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\(?video clip\)?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[?HQ(?: - Exclusive)?\]?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\bHD\s*1080p\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[?OUT NOW!?\]?', '', text, flags=re.IGNORECASE)
        # Remove years in parentheses or brackets e.g. (1992), [1999]
        text = re.sub(r'[\(\[]\d{4}[\]\)]', '', text)
        # Remove track number prefixes like "01 " or "15 - "
        text = re.sub(r'^\d{2}\s*-?\s*', '', text)
        # Remove code prefixes like "A-TP-", "C-S-", "AA-PR-"
        text = re.sub(r'^[A-Za-z]{1,2}-[A-Za-z]{1,2}-\s*', '', text)
        
        # Clean up any leftover double spaces, dangling hyphens at the end
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\s+-\s*$', '', text)
        return text.strip()

    def get_recovery_commands(self) -> List[str]:
        """Generates a list of shell commands to download missing tracks using tidal-dl-ng."""
        commands = []
        # Support custom tidal-dl-ng path via config or use system default
        td_bin = self.config.get("settings", {}).get("tidal_dl_path", "tidal-dl-ng")
        
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

    def run_recovery(self, dry_run: bool = False, quality: str = "LOSSLESS", temp_dir: Optional[str] = None):
        """Executes recovery commands or just prints them if dry_run is True."""
        # Note: Set default dry_run to False as requested by user (execution by default)
        
        # Configure quality in tidal-dl-ng before starting
        td_bin = self.config.get("settings", {}).get("tidal_dl_path", "tidal-dl-ng")
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
                import shutil
                import os
                import json
                from .metadata_handler import MetadataCloner
                from .crate_handler import CrateHandler
                
                download_base_dir = Path("./_recovery_temp") # Fallback
                
                if temp_dir:
                    download_base_dir = Path(temp_dir)
                else:
                    # Get the default tidal-dl download path if not explicitly provided
                    config_path = Path.home() / '.tidal-dl.json'
                    if config_path.exists():
                        try:
                            with open(config_path, 'r') as f:
                                td_config = json.load(f)
                                if 'downloadPath' in td_config:
                                    download_base_dir = Path(td_config['downloadPath'])
                        except Exception as e:
                            logging.warning(f"Could not parse tidal-dl config: {e}")
                
                download_base_dir.mkdir(parents=True, exist_ok=True)

                for i in range(0, len(commands), 2):
                    comment = commands[i] # # Track: /path/to/file
                    cmd = commands[i+1]    # tidal-dl ...
                    original_path_str = comment[9:] # Remove "# Track: "
                    original_path_obj = Path(original_path_str)
                    target_dir = original_path_obj.parent
                    
                    # Extract tidal_id from command
                    tidal_id = cmd.split("/track/")[-1].strip('"')
                    
                    is_tidal_import = original_path_str.startswith("TIDAL_IMPORT:")
                    
                    if is_tidal_import:
                        target_dir = download_base_dir
                    else:
                        if not target_dir.exists():
                            target_dir.mkdir(parents=True, exist_ok=True)
                        
                    print(f"\n==================================================")
                    print(f"Recuperando: {original_path_obj.name}")
                    if not is_tidal_import:
                        print(f"Destino: {target_dir}")
                    else:
                        print(f"Destino: Descarga directa (Tidal -> Serato)")
                    print(f"==================================================")
                    
                    try:
                        # 1. Check if the file already exists in download_base_dir
                        allowed_exts = {'.flac', '.mp3', '.mp4', '.m4a', '.wav'}
                        
                        # Get track info from DB to help matching
                        track_info = self.db.get_track_info(original_path_str.lstrip('/'))
                        display_name = track_info.get('display_name') if track_info else None
                        
                        found_file = None
                        # Try to find an existing file that matches
                        potential_files = list(download_base_dir.rglob("*"))
                        for f in potential_files:
                            if f.is_file() and f.suffix.lower() in allowed_exts and not f.name.startswith('.'):
                                # Matching logic:
                                # 1. Exact stem match with original
                                # 2. Contains tidal_id (if tidal-dl-ng was configured to include it, though unlikely)
                                # 3. Contains display_name parts
                                if f.stem.lower() == original_path_obj.stem.lower():
                                    found_file = f
                                    break
                                if display_name:
                                    # Very basic match: if a significant part of display_name is in the filename
                                    # We'll be conservative to avoid wrong matches
                                    clean_dname = self._clean_search_term(display_name).lower()
                                    if clean_dname in f.name.lower() or f.stem.lower() in clean_dname:
                                        found_file = f
                                        break
                        
                        if found_file:
                            print(f"ℹ️  Archivo encontrado en caché temporal: {found_file.name}")
                            new_files = [str(found_file.relative_to(download_base_dir))]
                        else:
                            # 2. Snapshot files in the download base dir before download
                            files_before = set(
                                str(f.relative_to(download_base_dir)) for f in download_base_dir.rglob("*") 
                                if f.is_file() and f.suffix.lower() in allowed_exts and not f.name.startswith('.')
                            )
                            
                            # Execute download
                            subprocess.run(cmd, shell=True, check=True)
                            
                            # Snapshot files after download
                            files_after = set(
                                str(f.relative_to(download_base_dir)) for f in download_base_dir.rglob("*") 
                                if f.is_file() and f.suffix.lower() in allowed_exts and not f.name.startswith('.')
                            )
                            new_files = list(files_after - files_before)
                        
                        if new_files:
                            # Assuming one file downloaded per command
                            downloaded_file = download_base_dir / new_files[0]
                            is_upgrade = False
                            
                            if is_tidal_import:
                                final_target_path = downloaded_file
                                markers = None
                            else:
                                # Construct final target path
                                final_target_filename = original_path_obj.stem + downloaded_file.suffix
                                final_target_path = target_dir / final_target_filename
                                
                                print("🔍 Extrayendo metadata y Serato Cue Points originales...")
                                markers = MetadataCloner.extract_serato_markers(str(original_path_obj))
                                
                                # Check if final target exists
                                if final_target_path.exists():
                                    backup_path = target_dir / f"BACKUP-{final_target_path.name}"
                                    print(f"⚠️  El archivo destino ya existe. Renombrando actual a: {backup_path.name}")
                                    final_target_path.rename(backup_path)
                                
                                if original_path_obj.exists() and original_path_obj != final_target_path:
                                    backup_path_original = target_dir / f"BACKUP-{original_path_obj.name}"
                                    print(f"⚠️  Renombrando archivo original a: {backup_path_original.name}")
                                    original_path_obj.rename(backup_path_original)
                                    is_upgrade = True
    
                                # Move downloaded file to final destination
                                shutil.move(str(downloaded_file), str(final_target_path))
                                
                                # Inject tags into the new file
                                if markers:
                                    success = MetadataCloner.inject_serato_markers(markers, str(final_target_path))
                                    if success:
                                        print("✅ Metadata de Serato clonada exitosamente.")
                                    else:
                                        print("⚠️  No se pudo inyectar la metadata de Serato.")
                                else:
                                    print("ℹ️  El archivo original no contenía metadata de Serato detectable.")
                            
                            print("🔄 Actualizando base de datos local y Crates de Serato...")
                            
                            # Call crate update functionality globally
                            config = self._load_config()
                            serato_dir = config.get("settings", {}).get("serato_base_dir", "/Users/jpardo/Downloads/_Serato_")

                            if is_tidal_import:
                                # ADD NEW TRACK TO TARGET CRATES
                                pending_crates = self.db.get_pending_crate_additions(tidal_id)
                                for c_path in pending_crates:
                                    c_handler = CrateHandler(c_path)
                                    if c_handler.add_track_to_crate(str(final_target_path)):
                                        print(f"✅ Se añadió el track al Crate: {Path(c_path).name}")
                                self.db.remove_pending_crate_additions(tidal_id)
                                
                                # Clean up placeholder mappings and register real file
                                self.db.update_track_status(original_path_str, 'synced', str(final_target_path))
                                self.db.upsert_track(str(final_target_path).lstrip('/'), tidal_id)
                                self.db.update_track_status(str(final_target_path).lstrip('/'), 'synced', str(final_target_path))
                                
                                print(f"🎉 Descarga (Tidal -> Serato) completada -> {final_target_path}")

                            else:
                                if original_path_str != str(final_target_path):
                                    crates_modified = CrateHandler.update_track_path_globally(
                                        serato_dir, 
                                        original_path_str, 
                                        str(final_target_path)
                                    )
                                    print(f"✅ Se actualizaron las referencias en {len(crates_modified)} Crates de Serato:")
                                    for c_name in crates_modified:
                                        print(f"   - {c_name}")
                                
                                if is_upgrade:
                                    # Old file goes to pending_cleanup, keep track of backup location
                                    self.db.update_track_status(original_path_str.lstrip('/'), 'pending_cleanup', str(backup_path_original))
                                    # Register new file as synced
                                    self.db.upsert_track(str(final_target_path).lstrip('/'), tidal_id)
                                    self.db.update_track_status(str(final_target_path).lstrip('/'), 'synced', str(final_target_path))
                                else:
                                    self.db.update_track_status(original_path_str.lstrip('/'), 'synced', str(final_target_path))
                                    
                                print(f"🎉 Descarga completada -> {final_target_path.name}")
                            
                        else:
                            print("ℹ️  No se detectó ningún archivo NUEVO en la ruta temporal.")
                            print("    (Si el FLAC ya existía allí de antes debido a un error previo, bórralo manualmente para que soundmirror pueda interceptar la nueva descarga completa).")
                            self.db.update_track_status(original_path_str.lstrip('/'), 'failed')
                            
                    except subprocess.CalledProcessError as e:
                        logging.error(f"Error al descargar: {e}")
                        self.db.update_track_status(original_path_str.lstrip('/'), 'failed')
                    except Exception as e:
                        logging.error(f"Error inesperado procesando {original_path_obj.name}: {e}")
                        self.db.update_track_status(original_path_str.lstrip('/'), 'failed')

            except KeyboardInterrupt:
                print("\n\nOperación cancelada por el usuario (Ctrl+C). Saliendo...")
                return

    def interactive_add_to_playlist(self, playlist_id: str, query: str):
        """Searches Tidal and adds a selected track to the specified playlist."""
        if not self.tidal.authenticate():
            logging.error("Failed to authenticate with Tidal.")
            return

        print(f"🔍 Buscando en Tidal: '{query}'")
        # Use search_tracks with a limit of 5 as requested
        results = self.tidal.search_tracks("", query, limit=5)
        
        if not results:
            print("❌ No se encontraron resultados en Tidal.")
            return
        
        print("\nResultados encontrados (máx 5):")
        for i, track in enumerate(results):
            artist_name = track.artist.name if hasattr(track, 'artist') and track.artist else "Unknown Artist"
            album_name = track.album.name if hasattr(track, 'album') and track.album else "Unknown Album"
            duration_min = track.duration // 60
            duration_sec = track.duration % 60
            print(f"[{i}] {artist_name} - {track.name} ({duration_min}:{duration_sec:02d}) [Album: {album_name}]")
        
        print(f"[{len(results)}] Cancelar")
        
        try:
            choice = input(f"\nSelecciona una opción (0-{len(results)}): ")
            if not choice.strip():
                print("❌ Operación cancelada.")
                return
                
            choice_idx = int(choice)
            if 0 <= choice_idx < len(results):
                selected_track = results[choice_idx]
                track_id = str(selected_track.id)
                
                print(f"➕ Añadiendo a la playlist: {selected_track.name} (ID: {track_id})")
                if self.tidal.add_tracks_to_playlist(playlist_id, [track_id]):
                    print(f"✅ Track añadido correctamente a Tidal.")
                    print(f"💡 El track aparecerá en Serato tras la próxima sincronización ('python run.py sync').")
                else:
                    print(f"❌ Error al añadir el track a la playlist de Tidal.")
            else:
                print("❌ Operación cancelada.")
        except ValueError:
            print("❌ Entrada no válida. Operación cancelada.")
        except Exception as e:
            print(f"❌ Error inesperado: {e}")

    def _create_orphan_crate(self, crate_name: str, tracks: List[str], subcrates_dir: Path):
        if not subcrates_dir.exists():
            logging.error(f"Cannot create orphan crate: Subcrates directory '{subcrates_dir}' not found.")
            return
        
        if not crate_name.endswith('.crate'):
            crate_name += '.crate'
            
        crate_path = subcrates_dir / crate_name
        handler = CrateHandler(str(crate_path))
        
        # Check existing tracks to prevent appending duplicates (optional, but good practice)
        existing_tracks = set()
        if crate_path.exists():
            try:
                for t in handler.get_tracks():
                    existing_tracks.add(t['local_path'])
            except Exception:
                pass
        
        added = 0
        for track_path in tracks:
            if track_path not in existing_tracks:
                if handler.add_track_to_crate(track_path):
                    added += 1
                
        if added > 0:
            logging.info(f"\033[93mAdded {added} missing tracks to Orphan Crate '{crate_name}'\033[0m")

if __name__ == "__main__":
    engine = SyncEngine()
    engine.run_sync()
