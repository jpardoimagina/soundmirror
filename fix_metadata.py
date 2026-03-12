import re

file_path = "src/tidal_serato_sync/metadata_handler.py"
with open(file_path, 'r') as f:
    content = f.read()

# Fix 1: MP3 GEOB Wrapper Reconstruction
old_mp3_geob = """                    # Serato GEOB
                    if key.startswith("GEOB") and hasattr(frame, 'desc') and frame.desc.startswith("Serato"):
                        clean_desc = frame.desc.replace('\\x00', '')
                        tags_extracted[clean_desc] = frame.data"""
new_mp3_geob = """                    # Serato GEOB
                    if key.startswith("GEOB") and hasattr(frame, 'desc') and frame.desc.startswith("Serato"):
                        clean_desc = frame.desc.replace('\\x00', '')
                        # Serato FLAC strictly requires the GEOB header embedded in the base64 string
                        wrapper = b'application/octet-stream\\x00\\x00' + clean_desc.encode('utf-8') + b'\\x00'
                        tags_extracted[clean_desc] = wrapper + frame.data"""
content = content.replace(old_mp3_geob, new_mp3_geob)

# Fix 2: MP4 `com.serato.dj` Extraction
# We need to NOT split off the payload wrapper for general markers,
# AND we need to handle playcount (base64) and relvol (plaintext) correctly!
old_mp4_extract = """                            try:
                                import re
                                b64_str = values[0] if isinstance(values[0], bytes) else str(values[0]).encode('ascii')
                                b64_str = re.sub(b'[^A-Za-z0-9+/]', b'', b64_str)
                                b64_str += b'=' * (-len(b64_str) % 4)
                                raw = base64.b64decode(b64_str)
                                
                                if desc_mapped in ["SERATO_PLAYCOUNT", "SERATO_RELVOL"]:
                                    tags_extracted[desc_mapped] = raw.split(b'\\x00')[0]
                                else:
                                    parts = raw.split(b'\\x00', 2)
                                    if len(parts) >= 3 and b'Serato' in parts[1]:
                                        tags_extracted[desc_mapped] = parts[2]
                                    else:
                                        tags_extracted[desc_mapped] = raw
                            except Exception as e:
                                logger.error(f"Error decoding base64 Serato tag {desc} in MP4: {e}")"""

new_mp4_extract = """                            try:
                                val_bytes = values[0] if isinstance(values[0], bytes) else str(values[0]).encode('ascii')
                                
                                if desc_mapped == "SERATO_RELVOL":
                                    # RelVol is often raw plaintext in MP4, e.g. b'0.000000'
                                    tags_extracted[desc_mapped] = val_bytes
                                elif desc_mapped == "SERATO_PLAYCOUNT":
                                    # Playcount is usually base64 e.g. 'MTgAC' -> '18'
                                    import re
                                    b64_str = re.sub(b'[^A-Za-z0-9+/]', b'', val_bytes)
                                    b64_str += b'=' * (-len(b64_str) % 4)
                                    raw = base64.b64decode(b64_str)
                                    # Strip null bytes and just keep numeric string
                                    tags_extracted[desc_mapped] = raw.split(b'\\x00')[0]
                                else:
                                    # Standard markers are full Base64 strings including the wrapper
                                    # We decode them to raw binary (with wrapper intact)
                                    import re
                                    b64_str = re.sub(b'[^A-Za-z0-9+/]', b'', val_bytes)
                                    b64_str += b'=' * (-len(b64_str) % 4)
                                    raw = base64.b64decode(b64_str)
                                    # Store exactly as decoded, FLAC will re-base64 encode it and Serato will rejoice
                                    tags_extracted[desc_mapped] = raw
                            except Exception as e:
                                logger.error(f"Error decoding Serato tag {desc} in MP4: {e}")"""
content = content.replace(old_mp4_extract, new_mp4_extract)

# Fix 3: MP4 Label condition (needed a .lower())
old_label_cond = "elif key == '\\xa9pub' or key.lower() == '----:com.apple.itunes:publisher' or key == '----:com.apple.itunes:label':"
new_label_cond = "elif key == '\\xa9pub' or key.lower() == '----:com.apple.itunes:publisher' or key.lower() == '----:com.apple.itunes:label':"
content = content.replace(old_label_cond, new_label_cond)

with open(file_path, 'w') as f:
    f.write(content)

