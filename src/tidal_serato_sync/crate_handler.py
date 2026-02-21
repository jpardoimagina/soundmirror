from pathlib import Path
from typing import List, Dict
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

    def replace_track_path(self, old_path: str, new_path: str) -> bool:
        """Modifies the crate file by replacing old_path with new_path.
        Returns True if the file was modified, False otherwise."""
        if not self.crate_path.exists():
            return False

        try:
            with open(self.crate_path, 'rb') as f:
                content = f.read()
            
            modified = False
            new_content = bytearray()
            pos = 0
            
            while pos < len(content):
                tag = content[pos:pos+4]
                tag_str = tag.decode('ascii', errors='ignore')
                length = struct.unpack('>I', content[pos+4:pos+8])[0]
                value = content[pos+8:pos+8+length]
                
                if tag_str == 'otrk':
                    # Parse otrk children
                    sub_pos = 0
                    new_otrk_value = bytearray()
                    otrk_modified = False
                    
                    while sub_pos < len(value):
                        sub_tag = value[sub_pos:sub_pos+4]
                        sub_tag_str = sub_tag.decode('ascii', errors='ignore')
                        sub_len = struct.unpack('>I', value[sub_pos+4:sub_pos+8])[0]
                        sub_val = value[sub_pos+8:sub_pos+8+sub_len]
                        
                        if sub_tag_str == 'ptrk':
                            path = sub_val.decode('utf-16-be').strip('\x00')
                            
                            # Normalize paths for comparison (Serato stores without leading slash)
                            norm_path = path.lstrip('/')
                            norm_old_path = old_path.lstrip('/')
                            
                            if norm_path == norm_old_path:
                                # Replace path
                                # Ensure the new path also follows Serato's format (no leading slash)
                                norm_new_path = new_path.lstrip('/')
                                new_val = norm_new_path.encode('utf-16-be')
                                new_len = len(new_val)
                                new_otrk_value.extend(sub_tag)
                                new_otrk_value.extend(struct.pack('>I', new_len))
                                new_otrk_value.extend(new_val)
                                otrk_modified = True
                                modified = True
                            else:
                                new_otrk_value.extend(value[sub_pos:sub_pos+8+sub_len])
                        else:
                            new_otrk_value.extend(value[sub_pos:sub_pos+8+sub_len])
                            
                        sub_pos += 8 + sub_len
                        
                    if otrk_modified:
                        new_content.extend(tag)
                        new_content.extend(struct.pack('>I', len(new_otrk_value)))
                        new_content.extend(new_otrk_value)
                    else:
                        new_content.extend(content[pos:pos+8+length])
                else:
                    new_content.extend(content[pos:pos+8+length])
                
                pos += 8 + length
                
            if modified:
                # Write back to file
                with open(self.crate_path, 'wb') as f:
                    f.write(new_content)
                return True
                
        except Exception as e:
            print(f"Error modifying crate {self.crate_path.name}: {e}")
            
        return False

    @staticmethod
    def list_all_crates(serato_dir: str) -> List[Path]:
        """
        Utility to list all available crates in a Serato directory.
        """
        subcrates_path = Path(serato_dir) / "Subcrates"
        if not subcrates_path.exists():
            return []
        
        return list(subcrates_path.glob("*.crate"))

    @staticmethod
    def update_track_path_globally(serato_dir: str, old_path: str, new_path: str) -> int:
        """
        Iterates all crates and replaces the track path.
        Returns the number of crates modified.
        """
        crates = CrateHandler.list_all_crates(serato_dir)
        modified_count = 0
        for crate_path in crates:
            handler = CrateHandler(str(crate_path))
            if handler.replace_track_path(old_path, new_path):
                modified_count += 1
        return modified_count

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
