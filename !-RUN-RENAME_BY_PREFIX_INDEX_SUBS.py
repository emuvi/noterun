# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import sys
import re
from typing import Optional

# Global variable for the number of zero-padded places in the index
INDEX_PADDING = 3

def is_already_prefixed(filename: str) -> bool:
    """
    Checks if the filename is already prefixed with the required format.
    """
    pattern = rf"^\[ .*? \] - \d{{{INDEX_PADDING}}} - "
    return bool(re.match(pattern, filename))

def generate_new_filename(filename: str, index: int, user_prefix: str) -> Optional[str]:
    """
    Generates the targeted standard filename with the user prefix and index.
    """
    if is_already_prefixed(filename):
        return None

    # Format the index with leading zeros based on INDEX_PADDING
    formatted_index = f"{index:0{INDEX_PADDING}d}"
    new_name = f"[ {user_prefix} ] - {formatted_index} - {filename}"
    
    return new_name

def get_safe_target_path(directory: str, filename: str) -> str:
    """
    Generates a unique file path within the given directory to avoid overwriting.
    """
    target_path = os.path.join(directory, filename)
    name_part, ext = os.path.splitext(filename)
    counter = 1
    
    while os.path.exists(target_path):
        new_name = f"{name_part} ({counter}){ext}"
        target_path = os.path.join(directory, new_name)
        counter += 1
        
    return target_path

def rename_file(filepath: str, directory: str, filename: str, index: int, user_prefix: str) -> bool:
    """
    Handles the prefixing and renaming operation for a single file.
    """
    try:
        new_name = generate_new_filename(filename, index, user_prefix)
        if not new_name:
            return True

        new_filepath = get_safe_target_path(directory, new_name)
        final_name = os.path.basename(new_filepath)
        
        print(f"[*] Renaming file...")
        print(f"    From: '{filepath}'")
        print(f"    To:   '{new_filepath}'")
        
        os.rename(filepath, new_filepath)
        print(f"[+] Successfully renamed '{filename}' to '{final_name}'.\n")
        return True
        
    except PermissionError as e:
        print(f"[-] Permission Denied renaming '{filepath}': {e}\n")
    except OSError as e:
        print(f"[-] OS Error renaming '{filepath}': {e}\n")
    except Exception as e:
        print(f"[-] Unexpected error renaming '{filepath}': {e}\n")
        
    return False

def filter_eligible_files(directory: str) -> list:
    """
    Scans the directory and subfolders for files that are eligible for renaming.
    """
    print(f"[*] Scanning directory '{directory}' and subfolders for files to rename...")
    eligible_files = []
    
    for dirpath, dirnames, filenames in os.walk(directory):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            
            # Ignore system/script files or .py/.url/.lnk files
            if filename.startswith('!-') or filename == os.path.basename(__file__) or filename.lower().endswith(('.py', '.url', '.lnk')):
                continue
                
            eligible_files.append((dirpath, filename))
        
    print(f"[+] Found {len(eligible_files)} eligible file(s) for renaming evaluation.\n")
    return eligible_files

def main():
    """
    Main execution function. Orchestrates the filtering and prefix-index-based renaming
    of files within the script's directory and its subfolders.
    """
    print("=" * 50)
    print("   Noterun Prefix-Index Rename Script (Recursive) Initialized")
    print("=" * 50)
    
    user_prefix = input("Enter the string to use as prefix: ").strip()
    if not user_prefix:
        print("[-] No prefix entered. Exiting.")
        return 0

    script_dir = os.path.dirname(os.path.abspath(__file__))
    files_to_process = filter_eligible_files(script_dir)
    
    if not files_to_process:
        print("[*] No files to process. Exiting.")
        return 0
        
    print("-" * 50)
    
    success_count = 0
    failure_count = 0
    
    # Sort files to ensure consistent indexing (alphabetically by full path)
    files_to_process.sort(key=lambda x: os.path.join(x[0], x[1]))
    
    # Find the maximum existing index to prevent duplications if new files are added
    max_existing_index = 0
    pattern = rf"^\[ .*? \] - (\d{{{INDEX_PADDING}}}) - "
    
    for dirpath, filename in files_to_process:
        match = re.match(pattern, filename)
        if match:
            try:
                idx = int(match.group(1))
                if idx > max_existing_index:
                    max_existing_index = idx
            except ValueError:
                pass
                
    current_index = max_existing_index + 1
    
    for dirpath, filename in files_to_process:
        filepath = os.path.join(dirpath, filename)
        
        if is_already_prefixed(filename):
            print(f"[*] Skipping file...")
            print(f"    File: '{filepath}'")
            print(f"    Reason: Already prefixed with a {INDEX_PADDING}-digit index.\n")
            success_count += 1
            continue
            
        if rename_file(filepath, dirpath, filename, current_index, user_prefix):
            success_count += 1
            current_index += 1
        else:
            failure_count += 1
            
    print("-" * 50)
    print(f"[*] Renaming process completed.")
    print(f"[+] Processed successfully: {success_count}")
    
    if failure_count > 0:
        print(f"[-] Errors encountered: {failure_count}")
        return 1
    else:
        print("[+] All files processed without errors!")
        return 0

if __name__ == '__main__':
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code)
