import base64
from pathlib import Path
from typing import Dict, Optional
import logging
from mutagen import File
from mutagen.flac import FLAC
from mutagen.mp4 import MP4

logger = logging.getLogger(__name__)

class MetadataCloner:
    """Clones Serato-specific metadata and DJ-critical tags between audio files."""
    
    @staticmethod
    def extract_serato_markers(source_path: str) -> Dict[str, bytes]:
        """Extracts Serato metadata and standard DJ tags from an audio file."""
        tags_extracted = {}
        try:
            audio = File(source_path)
            if audio is None:
                logger.warning(f"Unsupported audio format for metadata extraction: {source_path}")
                return tags_extracted

            # -- 1. If MP3 (has ID3 tags)
            if hasattr(audio, 'tags') and audio.tags and not isinstance(audio, (FLAC, MP4)):
                for key, frame in audio.tags.items():
                    # Serato GEOB
                    if key.startswith("GEOB") and hasattr(frame, 'desc') and frame.desc.startswith("Serato"):
                        clean_desc = frame.desc.replace('\x00', '')
                        # Serato FLAC strictly requires the GEOB header embedded in the base64 string
                        wrapper = b'application/octet-stream\x00\x00' + clean_desc.encode('utf-8') + b'\x00'
                        tags_extracted[clean_desc] = wrapper + frame.data
                        
                    # Standard tags
                    elif key == 'TKEY': tags_extracted['KEY'] = str(frame.text[0]).replace('\x00', '').encode('utf-8')
                    elif key == 'TBPM': tags_extracted['BPM'] = str(frame.text[0]).replace('\x00', '').encode('utf-8')
                    elif key == 'TCOM': tags_extracted['COMPOSER'] = str(frame.text[0]).replace('\x00', '').encode('utf-8')
                    elif key == 'TIT1': tags_extracted['GROUPING'] = str(frame.text[0]).replace('\x00', '').encode('utf-8')
                    elif key == 'TPUB': tags_extracted['LABEL'] = str(frame.text[0]).replace('\x00', '').encode('utf-8')
                    elif key.startswith('POPM'):
                        # mutagen's POPM frame has .rating (0-255) and .email
                        try:
                            tags_extracted[f'POPM_{frame.email}'] = str(frame.rating).encode('utf-8')
                        except Exception:
                            pass
                    elif key.startswith('COMM'):
                        if frame.text:
                            desc = getattr(frame, 'desc', '')
                            if 'itun' not in desc.lower():
                                tags_extracted['COMMENT'] = str(frame.text[0]).replace('\x00', '').encode('utf-8')
                    elif key.startswith('TXXX:'):
                        desc = getattr(frame, 'desc', '').upper()
                        if 'PLAYCOUNT' in desc: tags_extracted['SERATO_PLAYCOUNT'] = str(frame.text[0]).replace('\x00', '').encode('utf-8')
                        elif 'RELVOL' in desc: tags_extracted['SERATO_RELVOL'] = str(frame.text[0]).replace('\x00', '').encode('utf-8')

            # -- 2. If FLAC (has Vorbis comments)
            elif isinstance(audio, FLAC):
                if audio.tags:
                    for key, values in audio.tags.items():
                        key_lower = key.lower()
                        if key_lower.startswith("serato"):
                            try:
                                tags_extracted[key] = base64.b64decode(values[0])
                            except Exception as e:
                                logger.error(f"Error decoding base64 Serato tag {key} in FLAC: {e}")
                        elif key_lower in ['key', 'bpm', 'composer', 'grouping', 'comment', 'genre', 'label', 'publisher', 'rating']:
                            # Normalize publisher to label internally
                            tags_extracted['LABEL' if key_lower == 'publisher' else key_lower.upper()] = values[0].encode('utf-8')

            # -- 3. If MP4/M4A (has Atom tags)
            elif isinstance(audio, MP4):
                if audio.tags:
                    for key, values in audio.tags.items():
                        if key.startswith("----:com.serato.dj:"):
                            # MP4 stores them as e.g. "markers", "markersv2", "beatgrid"
                            # we map them to the standard GEOB desc used across MP3/FLAC
                            desc = key.split(":")[-1]
                            if desc == "markers": desc_mapped = "Serato Markers_"
                            elif desc == "markersv2": desc_mapped = "Serato Markers2"
                            elif desc == "beatgrid": desc_mapped = "Serato BeatGrid"
                            elif desc == "autgain": desc_mapped = "Serato Autotags"
                            elif desc == "overview": desc_mapped = "Serato Overview"
                            elif desc == "analysisVersion": desc_mapped = "Serato Analysis"
                            elif desc == "playcount": desc_mapped = "SERATO_PLAYCOUNT"
                            elif desc == "relvol": desc_mapped = "SERATO_RELVOL"
                            else: desc_mapped = "Serato " + desc.title()
                            
                            try:
                                val_bytes = values[0] if isinstance(values[0], bytes) else str(values[0]).encode('ascii')
                                
                                if desc_mapped == "SERATO_RELVOL":
                                    # RelVol is often raw plaintext in MP4, e.g. b'0.000000'
                                    tags_extracted[desc_mapped] = val_bytes
                                elif desc_mapped == "SERATO_PLAYCOUNT":
                                    # Playcount is usually base64 e.g. 'MTgAC' -> '18'
                                    import re
                                    b64_str = re.sub(b'[^A-Za-z0-9+/]', b'', val_bytes)
                                    # Fix invalid base64 lengths (e.g. MTgAC is 5 chars, round down to nearest 4)
                                    b64_str = b64_str[:len(b64_str) - (len(b64_str) % 4)]
                                    raw = base64.b64decode(b64_str)
                                    # Strip null bytes and just keep numeric string
                                    tags_extracted[desc_mapped] = raw.split(b'\x00')[0]
                                else:
                                    # Standard markers are full Base64 strings including the wrapper
                                    # We decode them to raw binary (with wrapper intact)
                                    import re
                                    b64_str = re.sub(b'[^A-Za-z0-9+/]', b'', val_bytes)
                                    b64_str = b64_str[:len(b64_str) - (len(b64_str) % 4)]
                                    raw = base64.b64decode(b64_str)
                                    # Store exactly as decoded, FLAC will re-base64 encode it and Serato will rejoice
                                    tags_extracted[desc_mapped] = raw
                            except Exception as e:
                                logger.error(f"Error decoding Serato tag {desc} in MP4: {e}")
                        elif key == '\xa9grp': tags_extracted['GROUPING'] = values[0].encode('utf-8')
                        elif key == '\xa9cmt': tags_extracted['COMMENT'] = values[0].encode('utf-8')
                        elif key == '\xa9gen': tags_extracted['GENRE'] = values[0].encode('utf-8')
                        elif key == '\xa9pub' or key.lower() == '----:com.apple.itunes:publisher' or key.lower() == '----:com.apple.itunes:label':
                            tags_extracted['LABEL'] = values[0] if isinstance(values[0], bytes) else str(values[0]).encode('utf-8')
                        elif key == 'rate' or key.lower() == '----:com.apple.itunes:rating':
                            tags_extracted['RATING'] = str(values[0]).encode('utf-8')
                        elif key == '----:com.apple.iTunes:KEY' or key == '----:com.apple.iTunes:initialkey':
                            tags_extracted['KEY'] = bytes(values[0])
                        elif key == 'tmpo':
                            tags_extracted['BPM'] = str(values[0]).encode('utf-8')

        except Exception as e:
            logger.error(f"Error extracting metadata from {source_path}: {e}")
            
        return tags_extracted

    @staticmethod
    def inject_serato_markers(markers: Dict[str, bytes], target_path: str) -> bool:
        """Injects Serato metadata into the target audio file (supports FLAC and MP3)."""
        if not markers:
            return False
            
        try:
            audio = File(target_path)
            if audio is None:
                logger.warning(f"Unsupported target format for metadata injection: {target_path}")
                return False

            if isinstance(audio, FLAC):
                for desc, data in markers.items():
                    if desc in ['KEY', 'BPM', 'COMPOSER', 'GROUPING', 'COMMENT', 'GENRE', 'LABEL', 'RATING']:
                        audio.tags[desc.lower()] = data.decode('utf-8', errors='ignore')
                    elif desc in ['SERATO_PLAYCOUNT', 'SERATO_RELVOL']:
                        audio.tags[desc.lower()] = data.decode('utf-8', errors='ignore')
                    elif desc.startswith('POPM_'):
                        audio.tags['rating'] = data.decode('utf-8', errors='ignore')
                    elif desc in ['TKEY', 'TBPM', 'TCOM', 'TIT1', 'COMM', 'TCON', 'TPUB']: 
                        mapping = {'TKEY':'key', 'TBPM':'bpm', 'TCOM':'composer', 'TIT1':'grouping', 'COMM':'comment', 'TCON':'genre', 'TPUB':'label'}
                        audio.tags[mapping[desc]] = data.decode('utf-8', errors='ignore')
                    elif "serato" in desc.lower():
                        if desc == "Serato Markers_": continue
                        
                        # Explicit Vorbis Serato keys: 
                        # 'Serato VidAssoc' -> 'serato_videoassociation', 'Serato Markers2' -> 'serato_markers_v2', etc.
                        if desc == "Serato VidAssoc": safe_key = "serato_videoassociation"
                        elif desc == "Serato RelVolAd": safe_key = "serato_relvol"
                        elif desc == "Serato Playcount": safe_key = "serato_playcount"
                        elif desc == "Serato Autotags": safe_key = "serato_autotags"
                        elif desc == "Serato Markers2": safe_key = "serato_markers_v2"
                        elif desc == "Serato BeatGrid": safe_key = "serato_beatgrid"
                        elif desc == "Serato Overview": safe_key = "serato_overview"
                        elif desc == "Serato Analysis": safe_key = "serato_analysis"
                        else: safe_key = desc.replace(' ', '_').lower()
                        b64_data = base64.b64encode(data).decode('ascii')
                        audio.tags[safe_key] = b64_data
                        
                        if safe_key == "serato_markers_v2":
                            audio.tags["serato_markers2"] = b64_data
                        
                audio.save()
                return True
                
            elif hasattr(audio, 'tags') and audio.tags is not None and not isinstance(audio, MP4):
                # ID3 injection
                from mutagen.id3 import GEOB, TKEY, TBPM, TCOM, TIT1, COMM, TCON, TPUB, TXXX
                try:
                    audio.add_tags()
                except Exception:
                    pass
                    
                for desc, data in markers.items():
                    decoded_data = data.decode('utf-8', errors='ignore')
                    
                    if desc == 'KEY': audio.tags.add(TKEY(encoding=3, text=[decoded_data]))
                    elif desc == 'BPM': audio.tags.add(TBPM(encoding=3, text=[decoded_data]))
                    elif desc == 'COMPOSER': audio.tags.add(TCOM(encoding=3, text=[decoded_data]))
                    elif desc == 'GROUPING': audio.tags.add(TIT1(encoding=3, text=[decoded_data]))
                    elif desc == 'COMMENT': audio.tags.add(COMM(encoding=3, lang='eng', desc='', text=[decoded_data]))
                    elif desc == 'GENRE': audio.tags.add(TCON(encoding=3, text=[decoded_data]))
                    elif desc == 'LABEL' or desc == 'TPUB': audio.tags.add(TPUB(encoding=3, text=[decoded_data]))
                    elif desc == 'SERATO_PLAYCOUNT': audio.tags.add(TXXX(encoding=3, desc='SERATO_PLAYCOUNT', text=[decoded_data]))
                    elif desc == 'SERATO_RELVOL': audio.tags.add(TXXX(encoding=3, desc='SERATO_RELVOL', text=[decoded_data]))
                    elif desc == 'RATING':
                        try:
                            from mutagen.id3 import POPM
                            audio.tags.add(POPM(encoding=3, email='serato.com', rating=int(decoded_data), count=0))
                        except Exception:
                            pass
                    elif desc.startswith('POPM_'):
                        try:
                            from mutagen.id3 import POPM
                            email = desc.split('_', 1)[1] if '_' in desc else 'serato.com'
                            audio.tags.add(POPM(encoding=3, email=email, rating=int(decoded_data), count=0))
                        except Exception:
                            pass
                    elif "serato" in desc.lower():
                        out_desc = desc
                        if out_desc.lower().startswith("serato_"):
                            out_desc = out_desc.replace('_', ' ').title().replace('Serato ', 'Serato ')
                            
                        audio.tags.add(GEOB(
                            encoding=0, 
                            mime='application/octet-stream', 
                            desc=out_desc, 
                            data=data
                        ))
                audio.save()
                return True
            else:
                logger.warning(f"Target file {target_path} does not support tagging via mutagen easily.")
                return False
                
        except Exception as e:
            logger.error(f"Error injecting metadata into {target_path}: {e}")
            return False
