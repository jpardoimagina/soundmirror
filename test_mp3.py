import sys
import base64
from mutagen import File

def inspect_file(filepath):
    audio = File(filepath)
    if not audio or not hasattr(audio, 'tags'):
        print("No tags found.")
        return
    
    print("Tags for", filepath)
    for key, frame in audio.tags.items():
        if key.startswith("GEOB"):
            desc = getattr(frame, 'desc', 'NoDesc')
            data = getattr(frame, 'data', b'')
            print(f"GEOB desc='{desc}' (len {len(desc)}), data len={len(data)}, type={type(data)}, starts={data[:20]}")
            if '\x00' in desc:
                print("  => WARNING: Null byte in desc!")
        elif key in ['TIT1', 'COMM', 'TPE1', 'TIT2'] or key.startswith('COMM'):
            text = getattr(frame, 'text', ['NoText'])[0]
            print(f"{key}: {repr(text)}")

if len(sys.argv) > 1:
    inspect_file(sys.argv[1])
else:
    print("Please provide a path to an MP3 file.")
