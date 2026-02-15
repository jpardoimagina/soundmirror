import argparse
import sys
import json
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
    subparsers.add_parser("discover", help="Escanea y registra todos los crates de Serato")

    # Command: add
    add_parser = subparsers.add_parser("add", help="Marca un crate para espejar en Tidal")
    add_parser.add_argument("index", type=int, help="Índice del crate (obtenido con 'list')")
    add_parser.add_argument("--name", help="Nombre personalizado para la lista en Tidal")

    # Command: sync
    sync_parser = subparsers.add_parser("sync", help="Ejecuta la sincronización")
    sync_parser.add_argument("--max-bitrate", type=int, help="Solo sincroniza canciones locales con bitrate menor o igual a este valor (kbps)")

    # Command: recover
    recover_parser = subparsers.add_parser("recover", help="Ejecuta la descarga de archivos faltantes")
    recover_parser.add_argument("--dry", action="store_true", help="Solo muestra lo que se descargaría")
    recover_parser.add_argument("--quality", choices=["LOW", "NORMAL", "HIGH", "LOSSLESS", "HI_RES_LOSSLESS"], 
                               default="LOSSLESS", help="Calidad de audio para la descarga")

    args = parser.parse_args()

    # Base dir for Serato
    serato_dir = "/Users/jpardo/Downloads/_Serato_"
    db = DatabaseManager()

    if args.command == "list":
        list_serato_crates(db, serato_dir)

    elif args.command == "discover":
        crates = CrateHandler.list_all_crates(serato_dir)
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
        engine.run_sync(max_bitrate=args.max_bitrate)

    elif args.command == "recover":
        engine = SyncEngine()
        engine.run_recovery(dry_run=args.dry, quality=args.quality)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
