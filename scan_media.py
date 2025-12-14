#!/usr/bin/env python3
"""
Media File Scanner and Duplicate Finder

Scans a directory recursively for image and video files,
computes SHA-256 hashes, detects duplicates, and generates a CSV report.
"""

import os
import sys
import hashlib
import argparse
import shutil
from pathlib import Path
from collections import defaultdict
try:
    from PIL import Image
    import imagehash
    PERCEPTUAL_HASH_AVAILABLE = True
except ImportError:
    PERCEPTUAL_HASH_AVAILABLE = False
    print("Warning: Pillow and/or imagehash not available. Perceptual hashing will be skipped.", file=sys.stderr)


# Supported file extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi'}


def compute_file_hash(file_path, chunk_size=8192):
    """
    Compute SHA-256 hash of a file.
    Reads file in chunks to handle large files efficiently.
    
    Args:
        file_path: Path to the file
        chunk_size: Size of chunks to read (default: 8KB)
    
    Returns:
        Hexadecimal string of the SHA-256 hash
    """
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            # Read file in chunks to handle large files efficiently
            while chunk := f.read(chunk_size):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except (IOError, OSError) as e:
        print(f"Error reading file {file_path}: {e}", file=sys.stderr)
        return None


def compute_perceptual_hash(file_path):
    """
    Compute perceptual hash (pHash) of an image file.
    
    Args:
        file_path: Path to the image file
    
    Returns:
        Hexadecimal string of the perceptual hash, or None if error or not available
    """
    if not PERCEPTUAL_HASH_AVAILABLE:
        return None
    
    try:
        with Image.open(file_path) as img:
            # Compute average hash (perceptual hash)
            phash = imagehash.average_hash(img)
            return str(phash)
    except (IOError, OSError, Exception) as e:
        print(f"Error computing perceptual hash for {file_path}: {e}", file=sys.stderr)
        return None


def hamming_distance(phash1, phash2):
    """
    Compute Hamming distance between two perceptual hashes.
    
    Args:
        phash1: First perceptual hash (string or imagehash object)
        phash2: Second perceptual hash (string or imagehash object)
    
    Returns:
        Hamming distance as integer, or None if error
    """
    if not PERCEPTUAL_HASH_AVAILABLE:
        return None
    
    try:
        # Convert strings to imagehash objects if needed
        if isinstance(phash1, str):
            phash1 = imagehash.hex_to_hash(phash1)
        if isinstance(phash2, str):
            phash2 = imagehash.hex_to_hash(phash2)
        
        return phash1 - phash2  # imagehash supports subtraction for Hamming distance
    except (ValueError, TypeError, Exception) as e:
        return None


def find_near_duplicate_groups(files_data, distance_threshold=20):
    """
    Group images by near-duplicate similarity using perceptual hash Hamming distance.
    Uses union-find to handle transitive relationships (if A is similar to B and B to C, all in same group).
    Compares each image's perceptual hash against every other image's perceptual hash.
    
    Args:
        files_data: List of file information dictionaries
        distance_threshold: Maximum Hamming distance to consider as near-duplicate (default: 20)
    
    Returns:
        Dictionary mapping file paths to near_duplicate_group_id
    """
    if not PERCEPTUAL_HASH_AVAILABLE:
        # If perceptual hashing not available, mark all as unique
        return {f['file_path']: 'unique' for f in files_data if f['file_type'] == 'image'}
    
    # Filter to only image files with valid phash
    image_files = [f for f in files_data if f['file_type'] == 'image' and f.get('phash')]
    
    if not image_files:
        return {}
    
    # Initialize all images as unique
    near_duplicate_groups = {f['file_path']: 'unique' for f in image_files}
    
    # Union-Find data structure for grouping
    parent = list(range(len(image_files)))
    
    def find(x):
        if parent[x] != x:
            parent[x] = find(parent[x])  # Path compression
        return parent[x]
    
    def union(x, y):
        root_x = find(x)
        root_y = find(y)
        if root_x != root_y:
            parent[root_y] = root_x
    
    # Compare all pairs and union similar images
    for i in range(len(image_files)):
        phash1 = image_files[i]['phash']
        if not phash1:
            continue
        
        for j in range(i + 1, len(image_files)):
            phash2 = image_files[j]['phash']
            if not phash2:
                continue
            
            distance = hamming_distance(phash1, phash2)
            if distance is not None and distance <= distance_threshold:
                union(i, j)
    
    # Group indices by their root
    groups = defaultdict(list)
    for i in range(len(image_files)):
        root = find(i)
        groups[root].append(i)
    
    # Assign group labels to groups with more than one image
    group_num = 1
    for root, indices in groups.items():
        if len(indices) > 1:
            group_label = f"nd_group_{group_num}"
            for idx in indices:
                file_path = image_files[idx]['file_path']
                near_duplicate_groups[file_path] = group_label
            group_num += 1
    
    return near_duplicate_groups


def add_near_duplicate_group_ids(files_data):
    """
    Add near_duplicate_group_id to each file based on perceptual hash similarity.
    
    Args:
        files_data: List of file information dictionaries
    
    Returns:
        Updated files_data with near_duplicate_group_id added
    """
    # Find near-duplicate groups
    near_duplicate_groups = find_near_duplicate_groups(files_data)
    
    # Add near_duplicate_group_id to each file
    for file_info in files_data:
        if file_info['file_type'] == 'image':
            file_path = file_info['file_path']
            file_info['near_duplicate_group_id'] = near_duplicate_groups.get(file_path, 'unique')
        else:
            # Non-image files don't have near_duplicate_group_id
            file_info['near_duplicate_group_id'] = ''
    
    return files_data


def get_file_type(file_path):
    """
    Determine file type based on extension.
    
    Args:
        file_path: Path to the file
    
    Returns:
        'image', 'video', or 'other'
    """
    ext = Path(file_path).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    elif ext in VIDEO_EXTENSIONS:
        return 'video'
    else:
        return 'other'


def scan_directory(directory_path):
    """
    Recursively scan directory for media files.
    
    Args:
        directory_path: Root directory to scan
    
    Returns:
        List of dictionaries containing file information
    """
    files_data = []
    directory_path = Path(directory_path)
    
    if not directory_path.exists():
        print(f"Error: Directory '{directory_path}' does not exist.", file=sys.stderr)
        sys.exit(1)
    
    if not directory_path.is_dir():
        print(f"Error: '{directory_path}' is not a directory.", file=sys.stderr)
        sys.exit(1)
    
    print(f"Scanning directory: {directory_path}")
    print("This may take a while for large directories...")
    
    # Walk through all files recursively
    for root, dirs, files in os.walk(directory_path):
        for file_name in files:
            file_path = Path(root) / file_name
            file_type = get_file_type(file_path)
            
            # Only process image and video files
            if file_type in ('image', 'video'):
                try:
                    file_size = file_path.stat().st_size
                    print(f"Processing: {file_path}")
                    
                    hash_value = compute_file_hash(file_path)
                    if hash_value:
                        # Compute perceptual hash for images only
                        phash_value = None
                        if file_type == 'image':
                            phash_value = compute_perceptual_hash(file_path)
                        
                        files_data.append({
                            'file_path': str(file_path),
                            'file_size_bytes': file_size,
                            'file_type': file_type,
                            'hash': hash_value,
                            'phash': phash_value if phash_value else ''
                        })
                except (OSError, IOError) as e:
                    print(f"Error processing {file_path}: {e}", file=sys.stderr)
                    continue
    
    return files_data


def find_duplicates(files_data):
    """
    Find duplicate files based on hash.
    
    Args:
        files_data: List of file information dictionaries
    
    Returns:
        Dictionary mapping hash to list of file paths
    """
    hash_to_files = defaultdict(list)
    
    for file_info in files_data:
        hash_value = file_info['hash']
        hash_to_files[hash_value].append(file_info['file_path'])
    
    # Filter to only include hashes with multiple files (duplicates)
    duplicates = {h: paths for h, paths in hash_to_files.items() if len(paths) > 1}
    
    return duplicates


def add_duplicate_group_ids(files_data):
    """
    Add duplicate_group_id to each file based on hash frequency.
    
    Args:
        files_data: List of file information dictionaries
    
    Returns:
        Updated files_data with duplicate_group_id added
    """
    # Count how many times each hash appears
    hash_counts = defaultdict(int)
    for file_info in files_data:
        hash_value = file_info['hash']
        hash_counts[hash_value] += 1
    
    # Add duplicate_group_id to each file
    for file_info in files_data:
        hash_value = file_info['hash']
        file_info['duplicate_group_id'] = hash_counts[hash_value]
    
    return files_data


def move_duplicates(files_data, duplicates, root_directory, destination_folder=None):
    """
    Move duplicate files to destination folder, preserving relative folder structure.
    For each duplicate group, keeps the first file as original and moves the rest.
    
    Args:
        files_data: List of file information dictionaries
        duplicates: Dictionary of duplicate groups (hash -> list of paths)
        root_directory: Root directory that was scanned (for computing relative paths)
        destination_folder: Destination folder path (default: duplicates_review/ next to root_directory)
    
    Returns:
        Tuple of (num_duplicate_groups, num_duplicates_moved, destination_path, errors)
        where errors is a list of error messages
    """
    root_directory = Path(root_directory).resolve()
    
    # Determine destination folder
    if destination_folder:
        destination_path = Path(destination_folder).resolve()
    else:
        # Default: duplicates_review/ next to the scanned directory
        destination_path = root_directory.parent / 'duplicates_review'
    
    # Create destination folder if it doesn't exist
    if not destination_path.exists():
        destination_path.mkdir(parents=True, exist_ok=True)
    
    num_duplicate_groups = len(duplicates)
    num_duplicates_moved = 0
    errors = []
    
    # Process each duplicate group
    for hash_value, file_paths in duplicates.items():
        # Sort paths to ensure consistent ordering (first file is original)
        sorted_paths = sorted(file_paths)
        original_path = sorted_paths[0]
        duplicate_paths = sorted_paths[1:]
        
        # Move each duplicate file
        for duplicate_path in duplicate_paths:
            try:
                source_path = Path(duplicate_path).resolve()
                if not source_path.exists():
                    errors.append(f"File not found: {duplicate_path}")
                    continue
                
                # Check if file is within root_directory to compute relative path
                try:
                    relative_path = source_path.relative_to(root_directory)
                    # Preserve folder structure
                    destination_file_path = destination_path / relative_path
                except ValueError:
                    # File is outside root_directory, just use filename
                    destination_file_path = destination_path / source_path.name
                
                # Create parent directories if needed
                destination_file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Handle filename conflicts by appending _1, _2, etc.
                if destination_file_path.exists():
                    stem = destination_file_path.stem
                    suffix = destination_file_path.suffix
                    counter = 1
                    while destination_file_path.exists():
                        new_filename = f"{stem}_{counter}{suffix}"
                        destination_file_path = destination_file_path.parent / new_filename
                        counter += 1
                
                # Move the file
                shutil.move(str(source_path), str(destination_file_path))
                num_duplicates_moved += 1
                
            except PermissionError as e:
                error_msg = f"Permission denied: {duplicate_path} - {str(e)}"
                errors.append(error_msg)
            except OSError as e:
                error_msg = f"File locked or error: {duplicate_path} - {str(e)}"
                errors.append(error_msg)
            except Exception as e:
                error_msg = f"Unexpected error moving {duplicate_path}: {str(e)}"
                errors.append(error_msg)
    
    return num_duplicate_groups, num_duplicates_moved, destination_path, errors


def print_summary(files_data, duplicates, move_results=None):
    """
    Print summary statistics.
    
    Args:
        files_data: List of file information dictionaries
        duplicates: Dictionary of duplicate groups
        move_results: Tuple of (num_duplicate_groups, num_duplicates_moved, duplicates_review_path) or None
    """
    total_files = len(files_data)
    total_images = sum(1 for f in files_data if f['file_type'] == 'image')
    total_videos = sum(1 for f in files_data if f['file_type'] == 'video')
    num_duplicate_groups = len(duplicates)
    num_files_in_duplicates = sum(len(paths) for paths in duplicates.values())
    
    # Calculate total duplicate files (extra copies only, not originals)
    unique_hashes = len(set(f['hash'] for f in files_data))
    total_duplicate_files = total_files - unique_hashes
    
    print("\n" + "="*60)
    print("SCAN SUMMARY")
    print("="*60)
    print(f"Total files scanned:     {total_files}")
    print(f"Total images:            {total_images}")
    print(f"Total videos:            {total_videos}")
    print(f"Number of duplicate groups: {num_duplicate_groups}")
    print(f"Number of files in duplicate groups: {num_files_in_duplicates}")
    print(f"Total duplicate files:   {total_duplicate_files}")
    print("="*60)
    
    if duplicates:
        print("\nDuplicate Groups:")
        for i, (hash_value, paths) in enumerate(duplicates.items(), 1):
            print(f"\nGroup {i} (hash: {hash_value[:16]}...):")
            for path in paths:
                print(f"  - {path}")
    
    # Print move summary if duplicates were moved
    if move_results:
        num_groups, num_moved, review_path, errors = move_results
        print("\n" + "="*60)
        print("DUPLICATE MOVE SUMMARY")
        print("="*60)
        print(f"Number of duplicate groups: {num_groups}")
        print(f"Number of duplicates moved: {num_moved}")
        print(f"Duplicates review folder:   {review_path}")
        if errors:
            print(f"\nErrors encountered ({len(errors)}):")
            for error in errors[:10]:  # Show first 10 errors
                print(f"  - {error}")
            if len(errors) > 10:
                print(f"  ... and {len(errors) - 10} more errors")
        print("="*60)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Scan directory for media files, compute hashes, and detect duplicates.'
    )
    parser.add_argument(
        'directory',
        type=str,
        help='Directory path to scan recursively'
    )
    parser.add_argument(
        '-d', '--destination',
        type=str,
        default=None,
        help='Destination folder for duplicates (default: duplicates_review/ next to scanned directory)'
    )
    
    args = parser.parse_args()
    
    # Scan directory
    files_data = scan_directory(args.directory)
    
    if not files_data:
        print("No image or video files found in the specified directory.")
        sys.exit(0)
    
    # Add duplicate_group_id to each file
    files_data = add_duplicate_group_ids(files_data)
    
    # Add near_duplicate_group_id to each file based on perceptual hash similarity
    files_data = add_near_duplicate_group_ids(files_data)
    
    # Find duplicates
    duplicates = find_duplicates(files_data)
    
    # Move duplicates to destination folder
    move_results = None
    if duplicates:
        move_results = move_duplicates(files_data, duplicates, args.directory, args.destination)
    
    # Print summary
    print_summary(files_data, duplicates, move_results)


if __name__ == '__main__':
    main()

