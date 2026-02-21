import base64
from pathlib import Path
from typing import Dict, Optional
import logging
from mutagen import File
from mutagen.flac import FLAC

logger = logging.getLogger(__name__)

class MetadataCloner:
    """Clones Serato-specific metadata (Cues, Beatgrids, etc.) between audio files."""
    
    @staticmethod
    def extract_serato_markers(source_path: str) -> Dict[str, bytes]:
        """Extracts Serato metadata from an audio file."""
        tags_extracted = {}
        try:
            audio = File(source_path)
            if audio is None:
                logger.warning(f"Unsupported audio format for metadata extraction: {source_path}")
                return tags_extracted

            # If MP3 (has ID3 tags)
            if hasattr(audio, 'tags') and audio.tags:
                for key, frame in audio.tags.items():
                    if key.startswith("GEOB") and hasattr(frame, 'desc') and frame.desc.startswith("Serato"):
                        tags_extracted[frame.desc] = frame.data
                        
                # Also extract Key and BPM if present
                for key in ['TKEY', 'TBPM', 'TCOM']:
                    if key in audio.tags:
                        tags_extracted[key] = audio.tags[key].text[0].encode('utf-8')
                        
            # If FLAC (has Vorbis comments)
            elif isinstance(audio, FLAC):
                for key, values in audio.tags.items():
                    if key.lower().startswith("serato"):
                        # In FLAC, Serato tags are base64 encoded strings
                        try:
                            tags_extracted[key] = base64.b64decode(values[0])
                        except Exception as e:
                            logger.error(f"Error decoding base64 Serato tag {key} in FLAC: {e}")
                            
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
                # Write to Vorbis comments as base64 strings
                for desc, data in markers.items():
                    if desc in ['TKEY', 'TBPM', 'TCOM']:
                        # Map to standard Vorbis comments
                        # FLAC keys: KEY, BPM, COMPOSER
                        flac_key = 'KEY' if desc == 'TKEY' else ('BPM' if desc == 'TBPM' else 'COMPOSER')
                        audio.tags[flac_key] = data.decode('utf-8', errors='ignore')
                    else:
                        # FLAC keys for Serato: e.g. "Serato Markers_" -> "serato_markers_"
                        safe_key = desc.replace(' ', '_').lower()
                        b64_data = base64.b64encode(data).decode('ascii')
                        audio.tags[safe_key] = b64_data
                        
                audio.save()
                return True
                
            elif hasattr(audio, 'tags') and audio.tags is not None:
                from mutagen.id3 import GEOB, TKEY, TBPM, TCOM
                try:
                    audio.add_tags()
                except Exception:
                    pass # Already has tags
                    
                for desc, data in markers.items():
                    if desc == 'TKEY':
                        audio.tags.add(TKEY(encoding=3, text=[data.decode('utf-8', errors='ignore')]))
                    elif desc == 'TBPM':
                        audio.tags.add(TBPM(encoding=3, text=[data.decode('utf-8', errors='ignore')]))
                    elif desc == 'TCOM':
                        audio.tags.add(TCOM(encoding=3, text=[data.decode('utf-8', errors='ignore')]))
                    else:
                        audio.tags.add(GEOB(
                            encoding=0, 
                            mime='application/octet-stream', 
                            desc=desc, 
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
