import csv
from pathlib import Path
from typing import List, Dict


class CSVHandler:
    """Handles reading and parsing of track information from CSV files."""

    def __init__(self, file_path: str):
        """
        Initialize the CSVHandler.

        :param file_path: Path to the CSV file.
        """
        self.file_path = Path(file_path)

    def parse_tracks(self) -> List[Dict[str, str]]:
        """
        Parses the tracks from the CSV file.

        :return: A list of dictionaries, each containing 'track_name' and 'artist_name'.
        :raises FileNotFoundError: If the CSV file does not exist.
        :raises ValueError: If the CSV file is empty or missing required columns.
        """
        if not self.file_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.file_path}")

        tracks = []
        with open(self.file_path, mode='r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            if not reader.fieldnames:
                raise ValueError("CSV file is empty or has no headers.")

            # Map possible header names
            field_map = {
                'track': next((f for f in reader.fieldnames if f.lower() in ['title', 'track_name', 'track']), None),
                'artist': next((f for f in reader.fieldnames if f.lower() in ['artist', 'artist_name']), None)
            }

            if not field_map['track'] or not field_map['artist']:
                raise ValueError(
                    f"CSV must contain track and artist headers. "
                    f"Found: {', '.join(reader.fieldnames)}"
                )

            for row in reader:
                track_name = row.get(field_map['track'], '').strip()
                artist_name = row.get(field_map['artist'], '').strip()
                
                if track_name and artist_name:
                    tracks.append({
                        'track_name': track_name,
                        'artist_name': artist_name
                    })

        if not tracks:
            raise ValueError("No valid tracks found in the CSV file.")

        return tracks


if __name__ == "__main__":
    # Example usage / quick test
    try:
        sample_path = "samples/tracks.csv"
        handler = CSVHandler(sample_path)
        parsed_tracks = handler.parse_tracks()
        print(f"Parsed {len(parsed_tracks)} tracks:")
        for t in parsed_tracks:
            print(f"- {t['track_name']} by {t['artist_name']}")
    except Exception as e:
        print(f"Error: {e}")
