import argparse
import sys
import json
import sqlite3
import struct
from pathlib import Path
from .crate_handler import CrateHandler
from .db_manager import DatabaseManager
from .sync_engine import SyncEngine
from .metadata_handler import MetadataCloner
from .drive_sync_manager import DriveSyncManager

def list_serato_crates(db, serato_dir, only_active: bool = False):
    mirrors = db.get_mirrors(only_active=False)  # Always get all to maintain indices
    if not mirrors:
        print("No se han descubierto crates. Ejecuta 'python src/cli.py discover' primero.")
        return []
    
    # Check if there are any mirrors to show if filtering
    if only_active and not any(m[3] for m in mirrors):
        print("No hay crates activos registrados.")
        return mirrors

    title = "Crates activos en la base de datos:" if only_active else "Crates en la base de datos:"
    print(f"\n{title}")
    for i, (path, tid, dir, active, name) in enumerate(mirrors):
        if only_active and not active:
            continue
        status = "[ACTIVO]" if active else "[INACTIVO]"
        print(f"[{i}] {status} {name}")
    return mirrors

def main():
    parser = argparse.ArgumentParser(description="Gestión de Sincronización Serato <-> Tidal")
    subparsers = parser.add_subparsers(dest="command")

    # Command: list
    list_parser = subparsers.add_parser("list", help="Lista los crates registrados en la DB")
    list_parser.add_argument("--active", action="store_true", help="Muestra solo los crates activos")

    # Command: discover
    discover_parser = subparsers.add_parser("discover", help="Escanea y registra todos los crates de Serato")
    discover_parser.add_argument("--serato-path", help="Ruta base de la carpeta _Serato_")

    # Command: add
    add_parser = subparsers.add_parser("add", help="Marca un crate para espejar en Tidal")
    add_parser.add_argument("index", type=int, help="Índice del crate (obtenido con 'list')")
    add_parser.add_argument("--name", help="Nombre personalizado para la lista en Tidal")

    # Command: sync
    sync_parser = subparsers.add_parser("sync", help="Ejecuta la sincronización")
    sync_parser.add_argument("--max-bitrate", type=int, help="Solo sincroniza canciones locales con bitrate menor o igual a este valor (kbps)")
    sync_parser.add_argument("--force-update", action="store_true", help="Fuerza pending_download en canciones existentes que cumplan el filtro de bitrate")
    sync_parser.add_argument("--orphan-crate", type=str, help="Nombre del crate para almacenar los tracks que no se encuentren en Tidal")
    sync_parser.add_argument("--interactive", action="store_true", help="Habilita la búsqueda interactiva para temas no encontrados")

    # Command: rm
    rm_parser = subparsers.add_parser("rm", help="Quita un crate de la lista de sincronización activa")
    rm_parser.add_argument("index", type=int, help="Índice del crate (obtenido con 'list')")

    # Command: reset
    reset_parser = subparsers.add_parser("reset", help="Mantiene el crate activo pero borra toda la info de los tracks de esa crate")
    reset_parser.add_argument("index", type=int, help="Índice del crate (obtenido con 'list')")

    # Command: compare
    compare_parser = subparsers.add_parser("compare", help="Compara un crate con su playlist de Tidal (diferencias)")
    compare_parser.add_argument("index", type=int, help="Índice del crate (obtenido con 'list')")

    # Command: recover
    recover_parser = subparsers.add_parser("recover", help="Ejecuta la descarga de archivos faltantes")
    recover_parser.add_argument("--dry", action="store_true", help="Solo muestra lo que se descargaría")
    recover_parser.add_argument("--quality", choices=["LOW", "NORMAL", "HIGH", "LOSSLESS", "HI_RES_LOSSLESS"], 
                               default="LOSSLESS", help="Calidad de audio para la descarga")
    recover_parser.add_argument("--temp-dir", type=str, help="Ruta temporal donde tidal-dl-ng deja las descargas (ej. /Users/jpardo/Music/Tracks)")

    # Command: list-tracks
    list_tracks_parser = subparsers.add_parser("list-tracks", help="Muestra el estado de todas las canciones en mapeo")
    list_tracks_parser.add_argument("--status", type=str, help="Filtrar por estado (ej. pending_download, synced, failed)")

    # Command: force
    force_parser = subparsers.add_parser("force", help="Fuerza el estado pending_download para una canción")
    force_parser.add_argument("path", type=str, help="Ruta de la canción (ej. /Users/.../archivo.mp3) o nombre parcial")

    # Command: cleanup
    cleanup_parser = subparsers.add_parser("cleanup", help="Borra del disco los archivos de backup antiguos (.bak) y limpia la base de datos")

    # Command: clear-tracks
    clear_tracks_parser = subparsers.add_parser("clear-tracks", help="Elimina TODOS los tracks locales de la lista de seguimiento (vacía la caché)")

    # Command: clear-track-mapping
    subparsers.add_parser("clear-track-mapping", help="Elimina TODOS los registros de mapeo de tracks de la base de datos")

    # Command: daemon
    daemon_parser = subparsers.add_parser("daemon", help="Ejecuta la sincronización en bucle infinito (Sync + Recover)")
    daemon_parser.add_argument("--interval", type=int, default=15, help="Intervalo en minutos (por defecto 15)")
    daemon_parser.add_argument("--orphan-crate", type=str, help="Nombre del crate para almacenar los tracks que no se encuentren en Tidal")

    # Command: googleupload
    googleupload_parser = subparsers.add_parser("googleupload", help="Sincroniza carpetas locales con Google Drive")
    googleupload_parser.add_argument("--source", help="Ruta local a sincronizar")
    googleupload_parser.add_argument("--dest", help="Nombre de la carpeta de destino en Google Drive")
    googleupload_parser.add_argument("--exclude", action='append', help="Patrón a excluir (ej: *.crate, _Serato_)")

    # Command: match
    match_parser = subparsers.add_parser("match", help="Busca un track en Tidal y lo añade al crate seleccionado")
    match_parser.add_argument("index", type=int, help="ID del crate (obtenido con 'list')")
    match_parser.add_argument("query", help="Patrón de búsqueda para el track en Tidal")

    # Command: upgrade
    upgrade_parser = subparsers.add_parser("upgrade", help="Clona metadatos y actualiza crates para un archivo mejorado (ej: MP3 -> FLAC)")
    upgrade_parser.add_argument("old", help="Ruta al archivo antiguo (o backup)")
    upgrade_parser.add_argument("new", help="Ruta al archivo nuevo")

    # Command: link
    link_parser = subparsers.add_parser("link", help="Vincula manualmente una playlist de Tidal a un crate de Serato")
    link_parser.add_argument("url", help="URL o ID de la playlist en Tidal")
    link_parser.add_argument("crate", help="Nombre o ruta del crate de Serato")

    # Command: track
    track_parser = subparsers.add_parser("track", help="Gestiona el estado de tracks individuales")
    track_subparsers = track_parser.add_subparsers(dest="track_command")

    # Command: track ignore
    ignore_parser = track_subparsers.add_parser("ignore", help="Ignora un track para evitar que sea procesado por recover")
    ignore_parser.add_argument("path_or_id", help="ID numérico o patrón/nombre de la canción a ignorar")

    # Command: track recover
    t_recover_parser = track_subparsers.add_parser("recover", help="Marca un track para ser recuperado (vuelve a pending_download)")
    t_recover_parser.add_argument("path_or_id", help="ID numérico o patrón/nombre de la canción a recuperar")

    args = parser.parse_args()

    # Load configuration
    config_path = Path("mirrors.json")
    config = {}
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except Exception as e:
            print(f"Advertencia: No se pudo leer mirrors.json: {e}")

    # Determine Base dir for Serato
    # Priority: 1. Args, 2. Config, 3. Default
    serato_dir = "/Users/jpardo/Downloads/_Serato_" # Default fallback
    
    if args.command == "discover" and args.serato_path:
        serato_dir = args.serato_path
    elif config.get("settings", {}).get("serato_base_dir"):
        serato_dir = config.get("settings", {}).get("serato_base_dir")
    
    # Ensure Path object and existence check for discover
    serato_path_obj = Path(serato_dir)
    
    db = DatabaseManager()

    if args.command == "list":
        list_serato_crates(db, serato_dir, only_active=args.active)

    elif args.command == "discover":
        if not serato_path_obj.exists():
            print(f"Error: La carpeta de Serato no existe en: {serato_dir}")
            print("Usa --serato-path para especificar la ubicación correcta o edita mirrors.json")
            return

        print(f"Escaneando crates en: {serato_dir}")
        crates = CrateHandler.list_all_crates(str(serato_path_obj))
        db.bulk_add_discovered_crates(crates)
        print(f"Se han registrado {len(crates)} crates en la base de datos (todos inactivos por defecto).")
        print("Usa 'list' para verlos y 'add' para activar la sincronización.")

    elif args.command == "add":
        mirrors = list_serato_crates(db, serato_dir)
        if 0 <= args.index < len(mirrors):
            crate_path, current_tid, _, _, _ = mirrors[args.index]
            playlist_name = args.name or Path(crate_path).stem
            db.add_mirror(crate_path, playlist_id=current_tid, direction="bidirectional", is_active=1)
            
            # Update mirrors.json
            config_path = Path("mirrors.json")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
            else:
                config = {"mirrors": [], "settings": {"serato_base_dir": serato_dir}}
                # Ensure settings dict exists if loaded but empty
                if "settings" not in config:
                    config["settings"] = {}
                if "serato_base_dir" not in config["settings"]:
                    config["settings"]["serato_base_dir"] = serato_dir
            
            # Check if already exists
            exists = False
            if "mirrors" in config:
                for m in config["mirrors"]:
                    if m["crate_path"] == str(crate_path):
                        exists = True
                        break
            
            if not exists:
                if "mirrors" not in config:
                    config["mirrors"] = []
                config["mirrors"].append({
                    "crate_path": crate_path,
                    "playlist_name": playlist_name,
                    "direction": "bidirectional"
                })
                with open(config_path, 'w') as f:
                    json.dump(config, f, indent=2)
                print(f"Crate '{Path(crate_path).name}' marcado para sincronización como '{playlist_name}'.")
            else:
                print(f"El crate '{Path(crate_path).name}' ya está marcado.")
        else:
            print("Índice fuera de rango.")

    elif args.command == "rm":
        mirrors = list_serato_crates(db, serato_dir)
        if 0 <= args.index < len(mirrors):
            crate_path, _, _, _, name = mirrors[args.index]
            
            # Deactivate in DB
            db.add_mirror(crate_path, playlist_id=None, is_active=0)
            
            # Remove from mirrors.json
            config_path = Path("mirrors.json")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                
                if "mirrors" in config:
                    initial_count = len(config["mirrors"])
                    config["mirrors"] = [m for m in config["mirrors"] if "crate_path" in m and m["crate_path"] != str(crate_path)]
                    if len(config["mirrors"]) < initial_count:
                        with open(config_path, 'w') as f:
                            json.dump(config, f, indent=2)
                        print(f"Crate '{name}' eliminado de mirrors.json.")
            
            print(f"✅ Crate '{name}' desactivado y quitado de la lista activa.")
        else:
            print("❌ Índice fuera de rango.")

    elif args.command == "reset":
        mirrors = list_serato_crates(db, serato_dir)
        if 0 <= args.index < len(mirrors):
            crate_path_str, _, _, is_active, name = mirrors[args.index]
            
            if not is_active:
                print(f"⚠️ El crate '{name}' ya está INACTIVO. No es necesario resetearlo.")
                sys.exit(0)
            
            print(f"🔄 Reseteando mappings para el crate: {name}")
            
            try:
                crate_handler = CrateHandler(crate_path_str)
                serato_tracks = crate_handler.get_tracks()
                paths_to_clear = [t['local_path'] for t in serato_tracks]
                
                if not paths_to_clear:
                    print("ℹ️ El crate está vacío en disco. Nada que limpiar.")
                else:
                    with sqlite3.connect(db.db_path) as conn:
                        cursor = conn.cursor()
                        # Use placeholders for the IN clause
                        placeholders = ','.join(['?'] * len(paths_to_clear))
                        cursor.execute(f"DELETE FROM track_mapping WHERE local_path IN ({placeholders})", paths_to_clear)
                        deleted_count = cursor.rowcount
                        conn.commit()
                        print(f"✅ Se han eliminado {deleted_count} registros de track_mapping para este crate.")
                        print(f"ℹ️ El crate '{name}' sigue ACTIVO y se re-sincronizará en la próxima ejecución.")
            except Exception as e:
                print(f"❌ Error durante el reset: {e}")
                sys.exit(1)
        else:
            print("❌ Índice fuera de rango.")

    elif args.command == "compare":
        mirrors = db.get_mirrors()
        if 0 <= args.index < len(mirrors):
            crate_path_str, tidal_playlist_id, direction, is_active, name = mirrors[args.index]
            if not is_active:
                print(f"❌ El crate '{name}' está marcado como INACTIVO. No se puede comparar.")
                sys.exit(1)
            if not tidal_playlist_id:
                print(f"❌ El crate '{name}' no tiene una playlist de Tidal asignada.")
                sys.exit(1)
            
            print(f"🔍 Comparando Crate: {name} con Playlist Tidal: {tidal_playlist_id}")
            
            try:
                crate_handler = CrateHandler(crate_path_str)
                serato_tracks = crate_handler.get_tracks()
            except Exception as e:
                print(f"❌ Error leyendo el crate: {e}")
                sys.exit(1)
            
            crate_tidal_ids = {}
            unmapped_local = []
            
            for track in serato_tracks:
                local_path = track['path']
                info = db.get_track_info(local_path)
                if info and info.get('tidal_id'):
                    crate_tidal_ids[str(info['tidal_id'])] = local_path
                else:
                    unmapped_local.append(local_path)
                    
            try:
                engine = SyncEngine()
                tidal_tracks = engine.tidal.get_playlist_tracks(tidal_playlist_id)
            except Exception as e:
                print(f"❌ Error leyendo la playlist de Tidal: {e}")
                sys.exit(1)
                
            tidal_ids = {str(track.id): track for track in tidal_tracks}
            
            missing_in_tidal = []
            missing_in_crate = []
            
            for tid, local_path in crate_tidal_ids.items():
                if tid not in tidal_ids:
                    missing_in_tidal.append((tid, local_path))
                    
            for tid, track in tidal_ids.items():
                if tid not in crate_tidal_ids:
                    missing_in_crate.append(track)
                    
            print("\n" + "="*60)
            print(f"📊 RESULTADOS DE LA COMPARACIÓN: {name}")
            print("="*60)
            print(f"🎵 Tracks en Crate local : {len(serato_tracks)}")
            print(f"🎵 Tracks en Playlist Tidal: {len(tidal_tracks)}")
            print("-" * 60)
            
            if not missing_in_tidal and not unmapped_local and not missing_in_crate:
                print("✅ ¡El Crate y la Playlist están PERFECTAMENTE SINCRONIZADOS!")
            else:
                if missing_in_tidal or unmapped_local:
                    print(f"\n❌ FALTAN EN TIDAL (Total: {len(missing_in_tidal) + len(unmapped_local)}):")
                    for tid, path in missing_in_tidal:
                        print(f"   - [Eliminado en Tidal?] {Path(path).name}")
                    for path in unmapped_local:
                        print(f"   - [No Mapeado/Local]    {Path(path).name}")
                
                if missing_in_crate:
                    print(f"\n❌ FALTAN EN EL CRATE (Total: {len(missing_in_crate)}):")
                    for track in missing_in_crate:
                        artist_name = track.artist.name if hasattr(track, 'artist') and track.artist else "Unknown Artist"
                        print(f"   - {artist_name} - {track.name}")
            print("="*60 + "\n")
        else:
            print("❌ Índice fuera de rango.")

    elif args.command == "sync":
        engine = SyncEngine()
        force_update = getattr(args, 'force_update', False)
        orphan_crate = getattr(args, 'orphan_crate', None)
        interactive = getattr(args, 'interactive', False)
        engine.run_sync(max_bitrate=args.max_bitrate, force_update=force_update, orphan_crate=orphan_crate, interactive=interactive)

    elif args.command == "recover":
        # Handle temp_dir from config or save new one
        if args.temp_dir:
            temp_dir = args.temp_dir
            if "settings" not in config:
                config["settings"] = {}
            if config["settings"].get("temp_dir") != temp_dir:
                config["settings"]["temp_dir"] = temp_dir
                try:
                    with open(config_path, 'w') as f:
                        json.dump(config, f, indent=2)
                    print(f"ℹ️  Directorio temporal guardado en configuración: {temp_dir}")
                except Exception as e:
                    print(f"⚠️  No se pudo guardar temp_dir: {e}")
        else:
            temp_dir = config.get("settings", {}).get("temp_dir")

        engine = SyncEngine()
        engine.run_recovery(dry_run=args.dry, quality=args.quality, temp_dir=temp_dir)

    elif args.command == "list-tracks":
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            if args.status:
                cursor.execute("SELECT id, local_path, status, bitrate, display_name FROM track_mapping WHERE status = ?", (args.status,))
            else:
                cursor.execute("SELECT id, local_path, status, bitrate, display_name FROM track_mapping")
                
            rows = cursor.fetchall()
            print(f"Total canciones encontradas: {len(rows)}\n")
            for tid, path, status, bitrate, dname in rows:
                bitrate_str = f" ({bitrate}kbps)" if bitrate else ""
                
                status_display = status.upper()
                if status == 'ignored':
                    status_display = "SYNCED"
                
                if path.startswith("TIDAL_IMPORT:"):
                    tidal_id = path.split(":")[-1]
                    name_str = dname if dname else "Unknown"
                    print(f"[{tid}] [{status_display}] TIDAL_IMPORT:{tidal_id} ({name_str}){bitrate_str}")
                else:
                    print(f"[{tid}] [{status_display}] {Path(path).name}{bitrate_str}")

    elif args.command == "force":
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT local_path FROM track_mapping WHERE local_path LIKE ?", (f"%{args.path}%",))
            matches = cursor.fetchall()
            
            if not matches:
                print(f"No se encontró ninguna canción que coincida con: {args.path}")
            elif len(matches) > 1:
                print(f"Búsqueda ambigua. Hay {len(matches)} canciones que coinciden:")
                for m in matches:
                    print(f"  - {m[0]}")
                print("Por favor, sé más específico.")
            else:
                target_path = matches[0][0]
                db.update_track_status(target_path, 'pending_download')
                print(f"✅ Canción forzada a pending_download:\n   {target_path}")

    elif args.command == "cleanup":
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT local_path, downloaded_path FROM track_mapping WHERE status = 'pending_cleanup'")
            rows = cursor.fetchall()
            
            if not rows:
                print("ℹ️  No hay archivos pendientes de limpieza.")
            else:
                deleted = 0
                for path, backup_path_str in rows:
                    if backup_path_str:
                        backup_file = Path(backup_path_str)
                        if backup_file.exists():
                            try:
                                backup_file.unlink()
                                print(f"🗑️  Borrado: {backup_file.name}")
                            except Exception as e:
                                print(f"⚠️  No se pudo borrar {backup_file.name}: {e}")
                    
                    # Delete the row from the database completely
                    cursor.execute("DELETE FROM track_mapping WHERE local_path = ?", (path,))
                    deleted += 1
                
                conn.commit()
                print(f"\n✅ Limpieza completada. {deleted} archivos/registros eliminados.")

    elif args.command == "clear-tracks":
        print("⚠️  ¡ATENCIÓN! Esto eliminara el registro de TODOS los tracks sincronizados en la base de datos local.")
        print("    Tendrás que volver a ejecutar 'sync' para que soundmirror escanee Serato de nuevo.")
        confirm = input("¿Estás seguro de querer vaciar la lista de tracks? (s/N): ")
        if confirm.lower() == 's':
            with sqlite3.connect(db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM track_mapping")
                deleted = cursor.rowcount
                conn.commit()
                print(f"🗑️  ¡Lista vaciada! (Se han eliminado {deleted} registros de seguimiento).")
        else:
            print("❌ Operación cancelada.")

    elif args.command == "clear-track-mapping":
        print("⚠️  ¡ATENCIÓN! Esto eliminará el mapeo de TODOS los tracks de la base de datos.")
        print("    Esto forzará a que soundmirror tenga que buscar de nuevo cada canción en Tidal.")
        confirm = input("¿Estás seguro de querer borrar todos los mapeos de tracks? (s/N): ")
        if confirm.lower() == 's':
            db.clear_all_track_mappings()
            print("🗑️  Mapeos de tracks eliminados correctamente.")
        else:
            print("❌ Operación cancelada.")

    elif args.command == "daemon":
        import time
        from datetime import datetime
        print(f"🚀 Iniciando daemon de sincronización (Intervalo: {args.interval} minutos)")
        while True:
            try:
                print(f"\n--- [ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ] ---")
                engine = SyncEngine()
                
                print("🔄 Ejecutando Sync...")
                orphan_crate = getattr(args, 'orphan_crate', None)
                engine.run_sync(max_bitrate=args.max_bitrate if hasattr(args, 'max_bitrate') else None, force_update=False, orphan_crate=orphan_crate)
                
                print("⏬ Ejecutando Recover (Calidad: LOSSLESS)...")
                config_path = Path("mirrors.json")
                temp_dir = None
                if config_path.exists():
                    try:
                        with open(config_path, 'r') as f:
                            cfg = json.load(f)
                        temp_dir = cfg.get("settings", {}).get("temp_dir")
                    except Exception:
                        pass
                
                engine.run_recovery(dry_run=False, quality="LOSSLESS", temp_dir=temp_dir)
                
                print(f"💤 Esperando {args.interval} minutos para la próxima ejecución...")
                time.sleep(args.interval * 60)
            except KeyboardInterrupt:
                print("\n🛑 Daemon detenido por el usuario.")
                break
            except Exception as e:
                print(f"❌ Error crítico en el daemon: {e}")
                print(f"🔄 Reintentando en {args.interval} minutos...")
                time.sleep(args.interval * 60)

    elif args.command == "googleupload":
        source = args.source or config.get("settings", {}).get("drive_sync_source")
        dest_folder_name = args.dest or config.get("settings", {}).get("drive_sync_dest")
        
        # Si el usuario puso una ruta (ej: /Volumes/.../Musica), nos quedamos solo con el nombre de la carpeta final
        if dest_folder_name and ("/" in dest_folder_name or "\\" in dest_folder_name):
            dest_folder_name = Path(dest_folder_name).name

        if not source or not dest_folder_name:
            print("❌ Error: Especifica origen y destino o defínelos en mirrors.json.")
            sys.exit(1)

        print(f"🔧 Iniciando Google Drive Sync...")
        try:
            credentials_path = config.get("settings", {}).get("drive_credentials_path")
            manager = DriveSyncManager(credentials_path=credentials_path)
        except Exception as e:
            print(f"❌ Error al conectar con Google Drive: {e}")
            sys.exit(1)

        print(f"📁 Buscando/Creando carpeta de destino: {dest_folder_name}")
        dest_id = manager.get_or_create_folder(dest_folder_name)
        
        excludes = args.exclude if args.exclude else ["*.crate", "_Serato_", "*.bak", ".DS_Store"]
        allowed_extensions = config.get("settings", {}).get("drive_allowed_extensions", ["mp3", "mp4", "flac", "3tc"])
        
        print(f"🚀 Iniciando sincronización recursiva...")
        print(f"📂 Origen: {source}")
        print(f"🚫 Exclusiones: {', '.join(excludes)}")
        print(f"🎵 Extensiones permitidas: {', '.join(allowed_extensions)}")
        
        try:
            manager.sync_folder_recursive(source, dest_id, excludes=excludes, allowed_extensions=allowed_extensions)
            print("\n✅ ¡Sincronización finalizada!")
        except Exception as e:
            print(f"\n❌ Error durante la sincronización: {e}")
            sys.exit(1)

    elif args.command == "match":
        mirrors = db.get_mirrors()
        if args.index < 0 or args.index >= len(mirrors):
            print(f"❌ ID de crate inválido: {args.index}")
            sys.exit(1)
            
        crate_path, playlist_id, _, _, name = mirrors[args.index]
        if not playlist_id:
            print(f"❌ El crate seleccionado ({name}) no tiene una playlist de Tidal asociada.")
            sys.exit(1)
            
        engine = SyncEngine()
        engine.interactive_add_to_playlist(playlist_id, args.query)

    elif args.command == "match-id":
        mirrors = db.get_mirrors()
        if args.index < 0 or args.index >= len(mirrors):
            print(f"❌ ID de crate inválido: {args.index}")
            sys.exit(1)
            
        crate_path, playlist_id, _, _, name = mirrors[args.index]
        if not playlist_id:
            print(f"❌ El crate seleccionado ({name}) no tiene una playlist de Tidal asociada.")
            sys.exit(1)
            
        # Extract ID from URL
        track_id = args.url.split("/track/")[-1].split("?")[0].strip("/")
        if not track_id.isdigit():
            print(f"❌ No se pudo extraer un ID válido de la URL: {args.url}")
            sys.exit(1)
            
        engine = SyncEngine()
        if engine.tidal.authenticate():
            print(f"➕ Añadiendo track {track_id} a la playlist de '{name}'...")
            if engine.tidal.add_tracks_to_playlist(playlist_id, [track_id]):
                print(f"✅ Track añadido correctamente.")
                print(f"💡 Aparecerá en Serato tras ejecutar 'sync'.")
            else:
                print(f"❌ Error al añadir el track.")

    elif args.command == "upgrade":
        old_path = Path(args.old).absolute()
        new_path = Path(args.new).absolute()

        print(f"\n" + "="*60)
        print(f"FORZANDO VINCULACIÓN Y METADATOS")
        print(f"Origen:  {old_path}")
        print(f"Destino: {new_path}")
        print("="*60 + "\n")

        if not old_path.exists():
            print(f"⚠️  ADVERTENCIA: No se encuentra el archivo de origen: {old_path}")
        
        if not new_path.exists():
            print(f"❌ ERROR: No se encuentra el archivo de destino: {new_path}")
            sys.exit(1)

        # 1. Clone Metadata
        print("1. 🔍 Extrayendo metadatos de Serato y puntos de Cue...")
        markers = MetadataCloner.extract_serato_markers(str(old_path))
        if markers:
            print(f"   - Se encontraron {len(markers)} marcadores. Inyectando en el nuevo fichero...")
            if MetadataCloner.inject_serato_markers(markers, str(new_path)):
                print("   ✅ Metadatos clonados con éxito.")
            else:
                print("   ❌ Error al inyectar metadatos.")
        else:
            print("   ℹ️  No se detectaron marcadores de Serato en el origen.")

        # 2. Update Crates
        print(f"2. 📦 Actualizando Crates de Serato en {serato_dir}...")
        modified_crates = CrateHandler.update_track_path_globally(
            serato_dir, 
            str(old_path), 
            str(new_path)
        )

        if modified_crates:
            print(f"   ✅ Se actualizaron {len(modified_crates)} crates:")
            for crate in modified_crates:
                print(f"      - {crate}")
        else:
            print("   ℹ️  No se encontraron referencias al archivo antiguo en ningún Crate.")

        # 3. Update Database
        print("3. 🗄️  Actualizando base de datos local...")
        db = DatabaseManager()
        old_track_info = db.get_track_info(str(old_path).lstrip('/'))
        if old_track_info and old_track_info.get('tidal_id'):
            tidal_id = old_track_info['tidal_id']
            display_name = old_track_info.get('display_name')
            
            db.upsert_track(str(new_path).lstrip('/'), tidal_id, display_name=display_name)
            db.update_track_status(str(new_path).lstrip('/'), 'synced', str(new_path))
            db.update_track_status(str(old_path).lstrip('/'), 'pending_cleanup', str(old_path))
            print(f"   ✅ Mapeo actualizado: {tidal_id} -> {new_path.name}")
        else:
            print("   ℹ️  El archivo antiguo no estaba registrado en la base de datos.")

        print("\n🎉 ¡Proceso completado!")

    elif args.command == "link":
        # Extract ID from URL
        playlist_id = args.url.split("/playlist/")[-1].split("?")[0].strip("/")
        
        # Resolve crate path
        crate_name = args.crate
        if not crate_name.endswith(".crate"):
            crate_name += ".crate"
            
        # If it's a full path, use it. Otherwise, look/create in Serato directory
        if "/" in args.crate or "\\" in args.crate:
            crate_path = Path(args.crate)
        else:
            crate_path = Path(serato_dir) / "Subcrates" / crate_name
            
        print(f"🔗 Vinculando Playlist '{playlist_id}' con Crate '{crate_path.name}'...")
        
        # Ensure it exists (create if not)
        if not crate_path.exists():
            print(f"📦 El crate no existe. Creando uno nuevo en: {crate_path}")
            handler = CrateHandler(str(crate_path))
            # add_track_to_crate triggers creation if doesn't exist. 
            # We can use a dummy track or just initialize it manually
            try:
                crate_path.parent.mkdir(parents=True, exist_ok=True)
                # Initialize basic crate structure
                handler = CrateHandler(str(crate_path))
                # Trigger internal creation by calling a method that writes if file missing
                handler.add_track_to_crate("dummy_track_placeholder")
                # Remove dummy track immediately to leave it empty
                # Actually, handler doesn't have a remove-track, but we can just write it with only header
                vrsn_str = '1.0/Serato ScratchLive Crate'
                vrsn_val = vrsn_str.encode('utf-16-be')
                vrsn_block = b'vrsn' + struct.pack('>I', len(vrsn_val)) + vrsn_val
                with open(crate_path, 'wb') as f:
                    f.write(vrsn_block)
            except Exception as e:
                print(f"❌ Error creando el crate: {e}")
                sys.exit(1)

        # Update DB
        db.add_mirror(str(crate_path), playlist_id=playlist_id, direction="bidirectional", is_active=1)
        
        # Update mirrors.json
        config_path = Path("mirrors.json")
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
        else:
            config = {"mirrors": [], "settings": {"serato_base_dir": serato_dir}}
            
        # Check if already exists
        exists = False
        if "mirrors" in config:
            for m in config["mirrors"]:
                if m["crate_path"] == str(crate_path):
                    m["playlist_id"] = playlist_id
                    exists = True
                    break
        
        if not exists:
            if "mirrors" not in config:
                config["mirrors"] = []
            config["mirrors"].append({
                "crate_path": str(crate_path),
                "playlist_id": playlist_id,
                "direction": "bidirectional"
            })
            
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
            
        print(f"✅ ¡Vinculado correctamente! Ejecuta 'sync' para sincronizar los temas.")

    elif args.command == "track":
        if not args.track_command:
            track_parser.print_help()
            sys.exit(0)

        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            
            # Check if it's an ID (numeric string)
            is_id = args.path_or_id.isdigit()
            if is_id:
                cursor.execute("SELECT local_path FROM track_mapping WHERE id = ?", (int(args.path_or_id),))
            else:
                cursor.execute("SELECT local_path FROM track_mapping WHERE local_path LIKE ?", (f"%{args.path_or_id}%",))
            
            matches = cursor.fetchall()
            
            if not matches:
                print(f"No se encontró ninguna canción que coincida con: {args.path_or_id}")
            elif len(matches) > 1:
                print(f"Búsqueda ambigua. Hay {len(matches)} canciones que coinciden:")
                for m in matches:
                    print(f"  - {m[0]}")
                print("Por favor, sé más específico o usa el ID numérico.")
            else:
                target_path = matches[0][0]
                if args.track_command == "ignore":
                    db.update_track_status(target_path, 'ignored')
                    print(f"✅ Canción marcada como SYNCED (ignorada para recover):\n   {target_path}")
                elif args.track_command == "recover":
                    db.update_track_status(target_path, 'pending_download')
                    print(f"✅ Canción marcada para RECUPERACIÓN:\n   {target_path}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
