# Usage Guide

The Tidal Playlist Creator allows you to create Tidal playlists from a CSV file.

## CSV Format

The CSV file should have a header row. It supports the following header names (case-insensitive):
- **Track**: `title`, `track_name`, or `track`.
- **Artist**: `artist` or `artist_name`.

Example:
```csv
title,artist
Bohemian Rhapsody,Queen
Imagine,John Lennon
...
```

## Running the Script

To create a playlist, run:

```bash
python run.py path/to/your/file.csv "Playlist Name"
```

### Options

- `--folder "Folder Name"`: Specify a Tidal folder to place the playlist in. If the folder exists, the playlist will be moved there.
- `--description "My Description"`: Provide a custom description.

## Authentication

When you run the script for the first time, it will provide a URL and a code.
1. Copy the URL into your browser.
2. Enter the code.
3. Log in to Tidal if prompted.
4. Your session will be saved for future use.
