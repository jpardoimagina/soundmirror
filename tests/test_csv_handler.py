import pytest
import csv
import os
from src.csv_handler import CSVHandler

def test_parse_valid_csv(tmp_path):
    d = tmp_path / "sub"
    d.mkdir()
    p = d / "test.csv"
    p.write_text("title,artist\nSong 1,Artist 1\nSong 2,Artist 2")
    
    handler = CSVHandler(str(p))
    tracks = handler.parse_tracks()
    
    assert len(tracks) == 2
    assert tracks[0]['track_name'] == "Song 1"
    assert tracks[0]['artist_name'] == "Artist 1"

def test_parse_empty_csv(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("track_name,artist_name")
    
    handler = CSVHandler(str(p))
    with pytest.raises(ValueError, match="No valid tracks found"):
        handler.parse_tracks()

def test_parse_missing_columns(tmp_path):
    p = tmp_path / "wrong.csv"
    p.write_text("wrong_col1,wrong_col2\nVal 1,Val 2")
    
    handler = CSVHandler(str(p))
    with pytest.raises(ValueError, match="CSV must contain track and artist headers"):
        handler.parse_tracks()

def test_file_not_found():
    handler = CSVHandler("non_existent.csv")
    with pytest.raises(FileNotFoundError):
        handler.parse_tracks()
