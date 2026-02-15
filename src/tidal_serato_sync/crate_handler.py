from pathlib import Path
from typing import List, Dict
import struct
import struct

class CrateHandler:
    """Handles reading and parsing of Serato .crate files manually."""

    def __init__(self, crate_path: str):
        self.crate_path = Path(crate_path)

    def get_tracks(self) -> List[Dict[str, str]]:
        if not self.crate_path.exists():
            raise FileNotFoundError(f"Crate file not found: {self.crate_path}")

        tracks = []
        try:
            with open(self.crate_path, 'rb') as f:
                content = f.read()
            
            pos = 0
            while pos < len(content):
                tag = content[pos:pos+4].decode('ascii', errors='ignore')
                length = struct.unpack('>I', content[pos+4:pos+8])[0]
                value = content[pos+8:pos+8+length]
                
                if tag == 'otrk':
                    # Inside 'otrk', look for 'ptrk'
                    sub_pos = 0
                    while sub_pos < len(value):
                        sub_tag = value[sub_pos:sub_pos+4].decode('ascii', errors='ignore')
                        sub_len = struct.unpack('>I', value[sub_pos+4:sub_pos+8])[0]
                        sub_val = value[sub_pos+8:sub_pos+8+sub_len]
                        
                        if sub_tag == 'ptrk':
                            # Paths are UTF-16BE
                            path = sub_val.decode('utf-16-be').strip('\x00')
                            tracks.append({'local_path': path})
                            break
                        sub_pos += 8 + sub_len
                
                pos += 8 + length
        except Exception as e:
            print(f"Error parsing crate {self.crate_path.name}: {e}")
            
        return tracks

    @staticmethod
    def list_all_crates(serato_dir: str) -> List[Path]:
        """
        Utility to list all available crates in a Serato directory.
        """
        subcrates_path = Path(serato_dir) / "Subcrates"
        if not subcrates_path.exists():
            return []
        
        return list(subcrates_path.glob("*.crate"))


if __name__ == "__main__":
    # Example usage / quick test
    import sys
    if len(sys.argv) > 1:
        handler = CrateHandler(sys.argv[1])
        try:
            tracks = handler.get_tracks()
            print(f"Found {len(tracks)} tracks in crate:")
            for t in tracks:
                print(f"- {t['local_path']}")
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("Usage: python crate_handler.py <path_to_crate>")
