# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import shutil
import sys
import time

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def print_error(message: str) -> None:
    """Prints an error message to stderr."""
    print(message, file=sys.stderr)


def get_safe_target_path(target_dir: str, filename: str) -> str:
    """
    Generates a safe target path to avoid overwriting existing files.
    Appends (1), (2), etc., to the filename if a file with the same name already exists.
    
    Args:
        target_dir (str): The directory where the file will be moved.
        filename (str): The original name of the file.
        
    Returns:
        str: A safe, unique file path in the target directory.
    """
    base, ext = os.path.splitext(filename)
    target_path = os.path.join(target_dir, filename)
    counter = 1
    
    while os.path.exists(target_path):
        new_name = f"{base} ({counter}){ext}"
        target_path = os.path.join(target_dir, new_name)
        counter += 1
        
    return target_path

def move_file(source_path: str, target_dir: str) -> bool:
    """
    Moves a single file to the target directory while handling potential naming collisions
    and file system errors.
    
    Args:
        source_path (str): The absolute path to the source file.
        target_dir (str): The absolute path to the destination directory.
        
    Returns:
        bool: True if the file was moved successfully, False otherwise.
    """
    filename = os.path.basename(source_path)
    last_error = None

    for attempt in range(1, 4):
        target_path = get_safe_target_path(target_dir, filename)
        if attempt == 1:
            print(f"[*] Moving '{filename}'...")
            print(f"    Source: {source_path}")
            print(f"    Target: {target_path}")
        try:
            shutil.move(source_path, target_path)
            print(f"[+] Successfully moved '{filename}'.\n")
            return True
        except FileNotFoundError as e:
            print_error(f"[-] File Not Found Error for '{filename}': {e}\n")
            return False
        except PermissionError as e:
            last_error = f"Permission Denied while moving '{filename}': {e}"
            if attempt < 3:
                time.sleep(0.4 * attempt)
                continue
        except OSError as e:
            last_error = f"OS Error while moving '{filename}': {e}"
            if attempt < 3:
                time.sleep(0.4 * attempt)
                continue
        except Exception as e:
            last_error = f"An unexpected error occurred while moving '{filename}': {e}"
            break

    print_error(f"[-] {last_error}\n")
    return False

def filter_eligible_files(directory: str) -> tuple:
    """
    Filters files in the given directory to find those eligible for moving.
    Ignores directories, the script itself, and files starting with '!-'.
    
    Args:
        directory (str): The directory to scan.
        
    Returns:
        tuple: (list of eligible filenames, bool indicating whether scanning succeeded)
    """
    print(f"[*] Scanning directory '{directory}' for files to move...")
    eligible_files = []
    
    try:
        files = os.listdir(directory)
    except PermissionError as e:
        print_error(f"[-] Permission Denied accessing directory '{directory}': {e}")
        return [], False
    except Exception as e:
        print_error(f"[-] Unexpected error accessing directory '{directory}': {e}")
        return [], False

    self_name = os.path.basename(__file__)
    self_bat = os.path.splitext(self_name)[0] + ".bat"

    for filename in files:
        filepath = os.path.join(directory, filename)

        # Only process files
        try:
            if not os.path.isfile(filepath):
                continue
        except OSError:
            continue

        # Skip system/script files or files explicitly marked with '!-RUN' or similar
        if filename.startswith('!-') or filename in (self_name, self_bat):
            print(f"[*] Skipping excluded script or system file: '{filename}'")
            continue

        eligible_files.append(filename)
        
    print(f"[+] Found {len(eligible_files)} eligible file(s) to move.\n")
    return eligible_files, True

def main():
    """
    Main execution function. Orchestrates the scanning, filtering, and moving
    of eligible files to the parent directory.
    """
    print("=" * 50)
    print("   Noterun Move to Parent Script Initialized")
    print("=" * 50)
    
    script_dir = os.getcwd()
    parent_dir = os.path.dirname(script_dir)
    
    print(f"[*] Current Directory: {script_dir}")
    print(f"[*] Target Parent Directory: {parent_dir}\n")

    if os.path.abspath(script_dir) == os.path.abspath(parent_dir):
        print_error("[-] Current directory has no parent directory (filesystem root). Aborting.")
        return 1

    files_to_move, scan_ok = filter_eligible_files(script_dir)
    if not scan_ok:
        return 1
    
    if not files_to_move:
        print("[*] No files to move. Exiting.")
        return 0
        
    print("-" * 50)
    
    success_count = 0
    failure_count = 0
    
    for filename in files_to_move:
        filepath = os.path.join(script_dir, filename)
        if move_file(filepath, parent_dir):
            success_count += 1
        else:
            failure_count += 1

    print("-" * 50)
    print(f"[*] Move process completed.")
    print(f"[+] Successful moves: {success_count}")
    
    if failure_count > 0:
        print_error(f"[-] Failed moves: {failure_count}")
        return 1
    else:
        print("[+] All files moved successfully!")
        return 0

if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[*] Process interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print_error(f"[-] Fatal error: {e}")
        sys.exit(1)
