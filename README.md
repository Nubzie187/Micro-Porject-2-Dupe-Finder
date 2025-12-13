# Duplicate Media Finder Web Interface

A local web application for finding duplicate images and videos in your directories.

## Features

- **Web-based interface**: Easy-to-use HTML interface
- **Directory scanning**: Recursively scans directories for media files
- **Exact duplicates**: Finds files with identical SHA-256 hashes
- **Near-duplicates**: Finds similar images using perceptual hashing
- **Clickable links**: All duplicate files are displayed as clickable links

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
   Navigate to `http://127.0.0.1:5000`

## Usage

1. Click the "Choose Directory" button and enter the full path to the directory you want to scan
2. Click "Scan for Duplicates" to start the scan
3. Wait for the scan to complete (this may take a while for large directories)
4. Review the results:
   - **Exact Duplicates**: Files with identical content (same hash)
   - **Near Duplicates**: Images that are visually similar
5. Click on any file path to open it in your default application

## How It Works

- The application uses your existing `scan_media.py` script
- It computes SHA-256 hashes for exact duplicate detection
- It uses perceptual hashing (pHash) for finding similar images
- Results are displayed in organized groups with clickable file links

## Notes

- File links use `file://` protocol - your browser may require permission to open local files
- Large directories may take several minutes to scan
- The application runs locally and doesn't send any data to external servers

