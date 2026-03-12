from mutagen import File
import pprint
audio = File("/Users/jpardo/Downloads/14 - Bennett - Vois sur ton chemin (Techno Mix).mp4")
if audio and hasattr(audio, 'tags'):
    for k, v in audio.tags.items():
        if isinstance(v, list) and len(v) > 0:
            if isinstance(v[0], bytes):
                print(f"{k} -> <bytes len {len(v[0])}>")
            else:
                try:
                    print(f"{k} -> {v[0].decode('utf-8', errors='ignore') if isinstance(v[0], bytes) else v[0]}")
                except Exception:
                    print(f"{k} -> {v[0]}")
        else:
            print(f"{k} -> {v}")
else:
    print("Tags not found.")
