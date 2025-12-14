#!/usr/bin/env python3
"""
Flask web application for duplicate media finder
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import os
import sys
import threading
from pathlib import Path

# Import functions from scan_media
from scan_media import (
    scan_directory,
    find_duplicates,
    add_duplicate_group_ids,
    add_near_duplicate_group_ids,
    move_duplicates
)

app = Flask(__name__)
CORS(app)  # Enable CORS for local file access

# Global variable to store selected directory (thread-safe with lock)
_dir_selection_lock = threading.Lock()
_selected_directory = None
_directory_selection_event = threading.Event()

@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template('index.html')

def _open_directory_picker():
    """Open native directory picker dialog"""
    global _selected_directory
    
    try:
        # Try tkinter first (works on Windows, Mac, Linux)
        try:
            import tkinter as tk
            from tkinter import filedialog
            
            # Create root window but hide it
            root = tk.Tk()
            root.withdraw()  # Hide the main window
            root.attributes('-topmost', True)  # Bring to front
            root.lift()  # Bring to front
            root.focus_force()  # Force focus
            
            # Open directory picker
            directory = filedialog.askdirectory(
                title="Select Directory to Scan",
                mustexist=True
            )
            
            root.destroy()
            
            if directory:
                with _dir_selection_lock:
                    _selected_directory = directory
                print(f'[DEBUG] Directory selected via tkinter: {directory}')
                return directory
            else:
                print('[DEBUG] User cancelled tkinter directory picker')
                return None
        except ImportError:
            # tkinter not available
            print('[DEBUG] tkinter not available')
        except Exception as e:
            print(f'[DEBUG] tkinter error: {e}')
            import traceback
            traceback.print_exc()
        
        # Fallback for Windows: use PowerShell
        if os.name == 'nt':
            try:
                import subprocess
                # Use PowerShell to show folder picker
                ps_script = '''
                Add-Type -AssemblyName System.Windows.Forms
                $folderBrowser = New-Object System.Windows.Forms.FolderBrowserDialog
                $folderBrowser.Description = "Select Directory to Scan"
                $folderBrowser.ShowNewFolderButton = $false
                if ($folderBrowser.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
                    Write-Output $folderBrowser.SelectedPath
                }
                '''
                result = subprocess.run(
                    ['powershell', '-Command', ps_script],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode == 0 and result.stdout.strip():
                    directory = result.stdout.strip()
                    with _dir_selection_lock:
                        _selected_directory = directory
                    print(f'[DEBUG] Directory selected via PowerShell: {directory}')
                    return directory
                else:
                    print('[DEBUG] PowerShell directory picker cancelled or failed')
            except Exception as e:
                print(f'[DEBUG] PowerShell error: {e}')
        
        print('[DEBUG] No directory picker method available')
        return None
    except Exception as e:
        print(f'[DEBUG] Error in directory picker: {e}')
        import traceback
        traceback.print_exc()
        return None

@app.route('/api/choose-directory', methods=['POST'])
def choose_directory():
    """Open native folder picker and return selected directory path"""
    global _selected_directory, _directory_selection_event
    
    print('[DEBUG] choose-directory endpoint called')
    
    try:
        # Reset selection
        with _dir_selection_lock:
            _selected_directory = None
        _directory_selection_event.clear()
        
        # Open directory picker in main thread (Flask runs in main thread)
        # For tkinter to work, we need to run it in the main thread
        directory = _open_directory_picker()
        
        if directory:
            print(f'[DEBUG] Returning selected directory: {directory}')
            return jsonify({'directory': directory})
        else:
            print('[DEBUG] No directory selected (user cancelled)')
            return jsonify({'error': 'No directory selected'}), 400
            
    except Exception as e:
        print(f'[DEBUG] Error in choose-directory: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/open-file', methods=['GET'])
def open_file():
    """Serve a file for opening in browser"""
    try:
        file_path = request.args.get('path')
        
        if not file_path:
            return jsonify({'error': 'No file path provided'}), 400
        
        # Decode the path
        import urllib.parse
        file_path = urllib.parse.unquote(file_path)
        file_path_obj = Path(file_path)
        
        if not file_path_obj.exists():
            return jsonify({'error': 'File does not exist'}), 404
        
        if not file_path_obj.is_file():
            return jsonify({'error': 'Path is not a file'}), 400
        
        # Determine MIME type
        import mimetypes
        mime_type, _ = mimetypes.guess_type(str(file_path_obj))
        if not mime_type:
            mime_type = 'application/octet-stream'
        
        # Serve the file
        from flask import send_file
        return send_file(
            str(file_path_obj),
            mimetype=mime_type,
            as_attachment=False,
            download_name=file_path_obj.name
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/move-file', methods=['POST'])
def move_file():
    """Move a single file to the destination folder, preserving folder structure"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        destination_folder = data.get('destination_folder')
        root_directory = data.get('root_directory')
        
        if not file_path:
            return jsonify({'error': 'No file path provided'}), 400
        
        if not destination_folder:
            return jsonify({'error': 'No destination folder provided'}), 400
        
        if not root_directory:
            return jsonify({'error': 'No root directory provided'}), 400
        
        source_path = Path(file_path).resolve()
        destination_path = Path(destination_folder).resolve()
        root_path = Path(root_directory).resolve()
        
        if not source_path.exists():
            return jsonify({'error': 'File does not exist'}), 404
        
        if not source_path.is_file():
            return jsonify({'error': 'Path is not a file'}), 400
        
        # Compute relative path to preserve folder structure
        try:
            relative_path = source_path.relative_to(root_path)
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
        import shutil
        shutil.move(str(source_path), str(destination_file_path))
        
        return jsonify({
            'success': True, 
            'message': f'File moved: {file_path}',
            'destination': str(destination_file_path),
            'original_path': str(source_path)  # Return original path for undo
        })
    except PermissionError as e:
        return jsonify({'error': f'Permission denied: {str(e)}'}), 403
    except OSError as e:
        return jsonify({'error': f'File locked or error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/undo-move', methods=['POST'])
def undo_move():
    """Undo a file move by moving it back to its original location"""
    try:
        data = request.get_json()
        destination_path = data.get('destination_path')
        original_path = data.get('original_path')
        
        if not destination_path:
            return jsonify({'error': 'No destination path provided'}), 400
        
        if not original_path:
            return jsonify({'error': 'No original path provided'}), 400
        
        dest_file = Path(destination_path).resolve()
        orig_file = Path(original_path).resolve()
        
        if not dest_file.exists():
            return jsonify({'error': 'Destination file does not exist'}), 404
        
        if not dest_file.is_file():
            return jsonify({'error': 'Destination path is not a file'}), 400
        
        # Create parent directories for original location if needed
        orig_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Move the file back
        import shutil
        shutil.move(str(dest_file), str(orig_file))
        
        return jsonify({
            'success': True, 
            'message': f'File moved back to original location: {original_path}',
            'original_path': str(orig_file)
        })
    except PermissionError as e:
        return jsonify({'error': f'Permission denied: {str(e)}'}), 403
    except OSError as e:
        return jsonify({'error': f'File locked or error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/scan', methods=['POST'])
def scan():
    """Scan directory for duplicates"""
    try:
        data = request.get_json()
        directory_path = data.get('directory')
        
        print(f'[DEBUG] scan API called with directory: {directory_path}')
        
        if not directory_path:
            print('[DEBUG] No directory provided in request')
            return jsonify({'error': 'No directory provided'}), 400
        
        # Validate directory exists
        directory_path = Path(directory_path)
        print(f'[DEBUG] Validating directory path: {directory_path}')
        
        if not directory_path.exists():
            print(f'[DEBUG] Directory does not exist: {directory_path}')
            return jsonify({'error': f'Directory does not exist: {directory_path}'}), 400
        
        if not directory_path.is_dir():
            print(f'[DEBUG] Path is not a directory: {directory_path}')
            return jsonify({'error': f'Path is not a directory: {directory_path}'}), 400
        
        print(f'[DEBUG] Starting scan of directory: {directory_path}')
        
        # Scan directory
        # Note: scan_directory may call sys.exit, but we've already validated the directory
        # so it should work. If it does exit, we'll catch it as a SystemExit exception.
        try:
            files_data = scan_directory(str(directory_path))
        except SystemExit as e:
            # scan_directory calls sys.exit on errors, convert to exception
            raise ValueError("Directory scan failed - directory may not exist or be invalid")
        
        if not files_data:
            return jsonify({
                'duplicates': [],
                'message': 'No media files found in the specified directory.'
            })
        
        # Add duplicate group IDs
        files_data = add_duplicate_group_ids(files_data)
        files_data = add_near_duplicate_group_ids(files_data)
        
        # Find exact duplicates (SHA-256 hash only, NOT near-duplicates/phash)
        duplicates = find_duplicates(files_data)
        
        # Get destination folder from request, or use default
        destination_folder = data.get('destination_folder')
        root_directory = str(directory_path)
        
        # If no destination folder provided, use default (duplicates_review/ next to scanned directory)
        if not destination_folder:
            root_path = Path(root_directory).resolve()
            destination_folder = str(root_path.parent / 'duplicates_review')
        
        # Format duplicates for frontend (only exact duplicates, no near-duplicates)
        duplicate_groups = []
        for hash_value, file_paths in duplicates.items():
            duplicate_groups.append({
                'hash': hash_value[:16] + '...',  # Shortened hash for display
                'files': [str(path) for path in file_paths],
                'count': len(file_paths)
            })
        
        # Prepare response (only exact duplicates, no near-duplicates)
        response_data = {
            'duplicates': duplicate_groups,
            'total_files': len(files_data),
            'total_duplicate_groups': len(duplicate_groups),
            'destination_folder': destination_folder,  # Return destination for individual file moves
            'root_directory': root_directory  # Return root directory for computing relative paths
        }
        
        return jsonify(response_data)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False, host='127.0.0.1', port=5055)

