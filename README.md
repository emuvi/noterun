# Noterun

Noterun is a collection of Python utility scripts designed to automate common file and media management tasks.

## Features

- **`!-RUN - ALL_LOAD.py`**: Fetches and updates the repository scripts directly from the `emuvi/noterun` GitHub repository.
- **`!-RUN - MOVE_PARENT.py`**: Moves files to their parent directories safely, automatically handling naming collisions by appending a counter (e.g., `(1)`).
- **`!-RUN - RENAME_FILES.py`**: Standardizes file names by parsing and prefixing them with their creation or modification dates.
- **`!-RUN - SPLIT_LARGE_MEDIA.py`**: Automatically splits large media files that exceed a specific size (default: 180MB) into smaller chunks.

## Prerequisites

- Python 3.x
- `ffmpeg` and `ffprobe` must be installed and available in your system's PATH (required for `SPLIT_LARGE_MEDIA.py`).

## Usage

You can run any of the utility scripts using Python from the command line or by double-clicking them (if Python is configured to execute `.py` files).

Example:
```bash
python "!-RUN - SPLIT_LARGE_MEDIA.py"
```
