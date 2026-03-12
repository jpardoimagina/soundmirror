import sys
import base64
from mutagen import File

mp4_path = "BACKUP-19 - Soft House Company - A Little Piano.mp4"
flac_path = "19 - Soft House Company - A Little Piano.flac"

mp4_audio = File(mp4_path)
flac_audio = File(flac_path)

if mp4_audio and flac_audio:
    mp4_val = mp4_audio.tags.get("----:com.serato.dj:markersv2", [b''])[0]
    flac_val = flac_audio.tags.get("serato_markers_v2", [""])[0]

    print("MP4 length:", len(mp4_val))
    print("FLAC length:", len(flac_val))
    
    import re
    mp4_clean = re.sub(b'[^A-Za-z0-9+/]', b'', mp4_val) + b'=' * (-len(re.sub(b'[^A-Za-z0-9+/]', b'', mp4_val)) % 4)
    flac_clean = re.sub(b'[^A-Za-z0-9+/]', b'', flac_val.encode('ascii')) + b'=' * (-len(re.sub(b'[^A-Za-z0-9+/]', b'', flac_val.encode('ascii'))) % 4)
    
    try:
        mp4_raw = base64.b64decode(mp4_clean)
        flac_raw = base64.b64decode(flac_clean)
        print("MP4 raw length:", len(mp4_raw))
        print("FLAC raw length:", len(flac_raw))
        print("Are raw payloads identical? ", mp4_raw == flac_raw)
        
        # if not identical, why?
        if mp4_raw != flac_raw:
            print("MP4 starts with:", mp4_raw[:50])
            print("FLAC starts with:", flac_raw[:50])
            print("Length diff:", len(flac_raw) - len(mp4_raw))
    except Exception as e:
        print("Error decoding:", e)

