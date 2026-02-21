import argparse
import sys
import json
import sqlite3
from pathlib import Path
from .crate_handler import CrateHandler
from .db_manager import DatabaseManager
from .sync_engine import SyncEngine

def list_serato_crates(db, serato_dir):
    mirrors = db.get_mirrors()
    if not mirrors:
        print("No se han descubierto crates. Ejecuta 'python src/cli.py discover' primero.")
        return []
    
    print("\nCrates en la base de datos:")
    for i, (path, tid, dir, active, name) in enumerate(mirrors):
        status = "[ACTIVO]" if active else "[INACTIVO]"
        print(f"[{i}] {status} {name}")
    return mirrors

def main():
    parser = argparse.ArgumentParser(description="Gestión de Sincronización Serato <-> Tidal")
    subparsers = parser.add_subparsers(dest="command")

    # Command: list
    subparsers.add_parser("list", help="Lista los crates registrados en la DB")

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
        list_serato_crates(db, serato_dir)

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

    elif args.command == "sync":
        engine = SyncEngine()
        force_update = getattr(args, 'force_update', False)
        engine.run_sync(max_bitrate=args.max_bitrate, force_update=force_update)

    elif args.command == "recover":
        engine = SyncEngine()
        engine.run_recovery(dry_run=args.dry, quality=args.quality, temp_dir=args.temp_dir)

    elif args.command == "list-tracks":
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            if args.status:
                cursor.execute("SELECT local_path, status, bitrate FROM track_mapping WHERE status = ?", (args.status,))
            else:
                cursor.execute("SELECT local_path, status, bitrate FROM track_mapping")
                
            rows = cursor.fetchall()
            print(f"Total canciones encontradas: {len(rows)}\n")
            for path, status, bitrate in rows:
                bitrate_str = f" ({bitrate}kbps)" if bitrate else ""
                print(f"[{status.upper()}] {Path(path).name}{bitrate_str}")

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
        print("⚠️  ¡ATENCIÓN! Esto eliminará el registro de TODOS los tracks sincronizados en la base de datos local.")
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

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
