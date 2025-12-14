# Duplicate Media Finder Web Interface

A local web application for finding duplicate images and videos in your directories and automatically organizing them.

## Features

- **Web-based interface**: Easy-to-use HTML interface
- **Directory scanning**: Recursively scans directories for media files
- **Exact duplicates**: Finds files with identical SHA-256 hashes
- **Near-duplicates**: Finds similar images using perceptual hashing
- **Automatic organization**: Moves duplicate files to a destination folder while preserving folder structure
- **Safe operation**: Keeps one original copy of each duplicate set in place

## Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Flask server**:
   ```bash
   python app.py
   ```

3. **Open your browser**:
   Navigate to `http://127.0.0.1:5055`

## How to Use

### Choosing the Destination Folder

1. **Select directory to scan**: Click "Choose Directory" or enter the path manually
2. **Choose destination folder** (optional):
   - Click "Choose Destination" to browse for a folder, or
   - Enter the destination path manually in the destination input field
   - If left empty, duplicates will be moved to `duplicates_review/` folder next to the scanned directory
3. **Start the scan**: Click "Scan for Duplicates"

### What Happens During a Scan

1. The tool scans the selected directory recursively for image and video files
2. Computes SHA-256 hashes to find exact duplicates
3. Computes perceptual hashes to find similar images
4. **Automatically moves duplicates**:
   - For each duplicate group, keeps the first file as the "original" in its original location
   - Moves all other duplicates to the destination folder
   - Preserves the relative folder structure (e.g., `Media/subfolder/image.jpg` → `destination/Media/subfolder/image.jpg`)
   - Handles filename conflicts by appending `_1`, `_2`, etc.

### After the Scan

The results page shows:
- **Total files scanned**: Number of media files found
- **Number of duplicate groups**: Groups of exact duplicates
- **Number of files moved**: Count of duplicate files moved
- **Destination folder**: Where duplicates were moved
- **Errors**: Any files that couldn't be moved (locked, permission denied, etc.)
- **Duplicate groups**: Lists of exact and near-duplicate files

## How It Works

- The application uses `scan_media.py` to scan and detect duplicates
- It computes SHA-256 hashes for exact duplicate detection
- It uses perceptual hashing (pHash) with Hamming distance ≤ 20 for finding similar images
- Duplicate files are moved using `shutil.move()` while preserving folder structure
- One original copy of each duplicate set remains in place

## Notes

- **No files are deleted**: Only moved to the destination folder
- **Folder structure preserved**: Relative paths are maintained in the destination folder
- **Safe defaults**: If no destination is specified, uses `duplicates_review/` next to the scanned directory
- Large directories may take several minutes to scan
- The application runs locally and doesn't send any data to external servers
- The `duplicates_review/` folder is automatically added to `.gitignore`

