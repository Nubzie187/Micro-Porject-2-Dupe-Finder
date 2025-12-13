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
    add_near_duplicate_group_ids
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

@app.route('/api/delete-file', methods=['POST'])
def delete_file():
    """Delete a file"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        
        if not file_path:
            return jsonify({'error': 'No file path provided'}), 400
        
        file_path_obj = Path(file_path)
        
        if not file_path_obj.exists():
            return jsonify({'error': 'File does not exist'}), 404
        
        if not file_path_obj.is_file():
            return jsonify({'error': 'Path is not a file'}), 400
        
        # Delete the file
        file_path_obj.unlink()
        
        return jsonify({'success': True, 'message': f'File deleted: {file_path}'})
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
        
        # Find duplicates
        duplicates = find_duplicates(files_data)
        
        # Format duplicates for frontend
        duplicate_groups = []
        for hash_value, file_paths in duplicates.items():
            duplicate_groups.append({
                'hash': hash_value[:16] + '...',  # Shortened hash for display
                'files': [str(path) for path in file_paths],
                'count': len(file_paths)
            })
        
        # Also find near-duplicates (perceptual hash groups)
        near_duplicate_groups = {}
        for file_info in files_data:
            if file_info.get('near_duplicate_group_id') and file_info['near_duplicate_group_id'] != 'unique':
                group_id = file_info['near_duplicate_group_id']
                if group_id not in near_duplicate_groups:
                    near_duplicate_groups[group_id] = []
                near_duplicate_groups[group_id].append(file_info['file_path'])
        
        # Filter near-duplicate groups to only include those with multiple files
        near_duplicate_list = []
        for group_id, file_paths in near_duplicate_groups.items():
            if len(file_paths) > 1:
                near_duplicate_list.append({
                    'group_id': group_id,
                    'files': file_paths,
                    'count': len(file_paths)
                })
        
        return jsonify({
            'duplicates': duplicate_groups,
            'near_duplicates': near_duplicate_list,
            'total_files': len(files_data),
            'total_duplicate_groups': len(duplicate_groups),
            'total_near_duplicate_groups': len(near_duplicate_list)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False, host='127.0.0.1', port=5055)

