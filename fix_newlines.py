import re

file_path = "src/tidal_serato_sync/metadata_handler.py"
with open(file_path, 'r') as f:
    content = f.read()

# Fix 1: Use base64.encodebytes instead of b64encode for Serato FLAC tags
old_b64 = """                        # Re-encode back to base64 for Vorbis comments
                        b64_data = base64.b64encode(data).decode('ascii')
                        audio.tags[safe_key] = b64_data"""

new_b64 = """                        # Re-encode back to base64 for Vorbis comments
                        # FLAC Serato tags must be MIME-wrapped at 76 chars, otherwise Serato fails/crashes!
                        b64_data = base64.encodebytes(data).decode('ascii').strip()
                        audio.tags[safe_key] = b64_data"""
content = content.replace(old_b64, new_b64)

# Fix 2: Ensure keys align perfectly
old_keys = """                    elif "serato" in desc.lower():
                        if desc.lower().startswith("serato_"):
                            safe_key = desc.lower()
                        else:
                            safe_key = desc.replace(' ', '_').lower()"""
new_keys = """                    elif "serato" in desc.lower():
                        # Explicit Vorbis Serato keys: 
                        # 'Serato VidAssoc' -> 'serato_videoassociation', 'Serato Markers_' -> 'serato_markers_', etc.
                        if desc == "Serato VidAssoc": safe_key = "serato_videoassociation"
                        elif desc == "Serato RelVolAd": safe_key = "serato_relvol"
                        elif desc == "Serato Playcount": safe_key = "serato_playcount"
                        elif desc == "Serato Autotags": safe_key = "serato_autotags"
                        elif desc == "Serato Markers2": safe_key = "serato_markers2"
                        else: safe_key = desc.replace(' ', '_').lower()"""
content = content.replace(old_keys, new_keys)

with open(file_path, 'w') as f:
    f.write(content)

