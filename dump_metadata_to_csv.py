import os
import sys
import csv
from mutagen import File

def get_snippet(val):
    if isinstance(val, list):
        if not val: return "[]"
        val = val[0]
    
    if isinstance(val, bytes):
        try:
            s = repr(val[:100])
        except:
            s = "bytes"
    elif isinstance(val, str):
        s = val.replace('\n', '\\n').replace('\r', '')[:100]
    else:
        s = str(val)[:100]
        
    return s + ("..." if hasattr(val, '__len__') and len(val) > 100 else "")

def dump_metadata(directory, output_csv):
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        header = ["File_Name", "File_Type", "Tag_Category", "Tag_Key", "Sub_Desc", "Value_Type", "Value_Length", "Data_Snippet"]
        writer.writerow(header)
        
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(('.mp3', '.mp4', '.m4a', '.flac')):
                    filepath = os.path.join(root, file)
                    ext = os.path.splitext(file)[1].lower()
                    
                    try:
                        audio = File(filepath)
                        if not audio or getattr(audio, 'tags', None) is None:
                            writer.writerow([file, ext, "Error/NoTags", "", "", "", 0, "No tags found"])
                            continue
                        
                        for key, tag in audio.tags.items():
                            category = "ID3" if ext == '.mp3' else ("Vorbis" if ext == '.flac' else "MP4 Atom")
                            desc = ""
                            val_type = type(tag).__name__
                            val = tag
                            
                            # Introspect ID3 Frames (MP3)
                            if ext == '.mp3':
                                desc = getattr(tag, 'desc', '')
                                if hasattr(tag, 'data'):
                                    val = tag.data
                                    val_type = "binary (data)"
                                elif hasattr(tag, 'text'):
                                    val = tag.text
                                    val_type = "text array"
                                elif hasattr(tag, 'email') and hasattr(tag, 'rating'):
                                    val = f"Email: {tag.email}, Rating: {tag.rating}"
                                    val_type = "POPM Frame"
                                else:
                                    val = str(tag)
                            # Introspect Vorbis Comments (FLAC)
                            elif ext == '.flac':
                                if isinstance(val, list) and len(val) > 0:
                                    val = val[0]
                                    val_type = "str list"
                            # Introspect MP4 Atoms
                            else:
                                if isinstance(val, list) and len(val) > 0:
                                    val = val[0]
                                    val_type = type(val).__name__
                                    
                            length = len(val) if hasattr(val, '__len__') else 0
                            snippet = get_snippet(val)
                            
                            writer.writerow([file, ext, category, key, desc, val_type, length, snippet])
                            
                    except Exception as e:
                        writer.writerow([file, ext, "Error", "Exception", "", str(type(e)), 0, str(e)])
                        print(f"Error reading {filepath}: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python dump_metadata_to_csv.py <ruta_del_directorio>")
        sys.exit(1)
    
    directory = sys.argv[1]
    output_csv = "metadata_dump.csv"
    print(f"Buscando MP3/MP4/M4A/FLAC en: {directory}")
    dump_metadata(directory, output_csv)
    print(f"✅ ¡Completado! Tienes los resultados en {output_csv}")
