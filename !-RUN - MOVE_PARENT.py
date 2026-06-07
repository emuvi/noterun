import os
import shutil

def get_safe_target_path(target_dir, filename):
    """
    Generates a safe target path avoiding overwriting existing files.
    Appends (1), (2), etc. if the file already exists.
    """
    base, ext = os.path.splitext(filename)
    target_path = os.path.join(target_dir, filename)
    counter = 1
    
    while os.path.exists(target_path):
        new_name = f"{base} ({counter}){ext}"
        target_path = os.path.join(target_dir, new_name)
        counter += 1
        
    return target_path

def move_file(source_path, target_dir):
    """
    Moves a single file to the target directory with collision handling.
    Catches and logs permission or file not found errors.
    """
    filename = os.path.basename(source_path)
    target_path = get_safe_target_path(target_dir, filename)
    
    print(f"[INFO] Moving:\n  Source: '{source_path}'\n  Target: '{target_path}'")
    try:
        shutil.move(source_path, target_path)
        print(f"[SUCCESS] Moved '{filename}' successfully.\n")
    except PermissionError as e:
        print(f"[ERROR] Permission denied when moving '{filename}': {e}\n")
    except FileNotFoundError as e:
        print(f"[ERROR] File not found when moving '{filename}': {e}\n")
    except Exception as e:
        print(f"[ERROR] Unexpected error moving '{filename}': {e}\n")

def process_directory(directory):
    """
    Iterates through the directory and moves eligible files to the parent directory.
    Ignores directories, scripts, and explicitly excluded files.
    """
    parent_dir = os.path.dirname(directory)
    print(f"[START] Processing directory: '{directory}'")
    print(f"[START] Target parent directory: '{parent_dir}'\n")

    try:
        files = os.listdir(directory)
    except PermissionError as e:
        print(f"[FATAL] Permission denied accessing directory '{directory}': {e}")
        return
    except Exception as e:
        print(f"[FATAL] Unexpected error accessing directory '{directory}': {e}")
        return

    for filename in files:
        filepath = os.path.join(directory, filename)

        # Skip directories
        if not os.path.isfile(filepath):
            continue

        # Skip scripts and excluded files
        if filename.startswith('!-') or filename == os.path.basename(__file__):
            print(f"[SKIP] Ignoring excluded file: '{filename}'")
            continue

        move_file(filepath, parent_dir)

    print(f"[FINISHED] Directory processing completed for '{directory}'.")

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    process_directory(script_dir)
    input()
