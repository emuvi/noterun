# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import re
import sys
import datetime
from typing import Optional, Tuple

def parse_date_prefix(filename: str) -> Tuple[Optional[datetime.datetime], str, Optional[str]]:
    """
    Attempts to parse date/time prefix from the filename based on known formats.
    """
    formats = [
        "%Y.%m.%d-%H.%M", "%Y.%m.%d_%H.%M.%S", "%Y-%m-%d_%H-%M-%S", "%Y.%m.%d %H.%M.%S",
        "%Y-%m-%d %H:%M:%S", "%Y.%m.%d-%H.%M.%S", "%Y.%m.%d",
        "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y",
        "%Y%m%d_%H%M%S", "%Y%m%d",
        "%Y.%m.%d %H.%M", "%Y-%m-%d %H.%M", "%Y-%m-%d_%H.%M",
        "%Y%m%d%H%M%S", "%Y%m%d%H%M"
    ]
    
    for length in range(25, 7, -1):
        if length > len(filename):
            continue
        prefix = filename[:length]
        for fmt in formats:
            try:
                dt = datetime.datetime.strptime(prefix, fmt)
                rest = filename[length:]
                
                if rest.startswith(' - '):
                    return dt, rest[3:], fmt
                elif rest.startswith('- ') or rest.startswith(' -'):
                    return dt, rest[2:], fmt
                elif rest.startswith(' ') or rest.startswith('-') or rest.startswith('_'):
                    return dt, rest[1:], fmt
                else:
                    return dt, rest, fmt
            except ValueError:
                continue
    return None, filename, None

def remove_time_from_filename(filename: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Checks if the filename contains any known time format added by the rename scripts
    and removes it, preserving prefixes and the rest of the filename.
    
    Args:
        filename (str): The current name of the file.
        
    Returns:
        tuple: (new_name, skip_reason). The newly generated filename, or None if no change is needed/possible.
    """
    # Check if there's a user prefix like "[ PREFIX ] - "
    match = re.match(r"^(\\[ .*? \\] - )(.*)$", filename)
    if match:
        prefix_part = match.group(1)
        name_to_parse = match.group(2)
    else:
        prefix_part = ""
        name_to_parse = filename
        
    dt, rest_part, fmt = parse_date_prefix(name_to_parse)
    if dt:
        if not rest_part:
            return None, "Removing time would leave file without name/extension"
        return f"{prefix_part}{rest_part}", None
        
    return None, "No matching time format found in filename"

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

def rename_file(filepath: str, directory: str, filename: str) -> bool:
    """
    Handles the operation to remove time from a single file's name.
    """
    try:
        new_name, skip_reason = remove_time_from_filename(filename)
        if not new_name:
            print(f"[*] Skipping file...")
            print(f"    File: '{filepath}'")
            print(f"    Reason: {skip_reason}\n")
            return True

        new_filepath = get_safe_target_path(directory, new_name)
        final_name = os.path.basename(new_filepath)
        
        print(f"[*] Renaming file...")
        print(f"    From: '{filepath}'")
        print(f"    To:   '{new_filepath}'")
        
        os.rename(filepath, new_filepath)
        print(f"[+] Successfully renamed to '{final_name}'.\n")
        return True
        
    except PermissionError as e:
        print(f"[-] Permission Denied renaming '{filename}': {e}\n")
    except OSError as e:
        print(f"[-] OS Error renaming '{filename}': {e}\n")
    except Exception as e:
        print(f"[-] Unexpected error renaming '{filename}': {e}\n")
        
    return False

def filter_eligible_files(base_directory: str) -> list:
    """
    Scans the directory and subdirectories for files that are eligible for renaming.
    """
    print(f"[*] Scanning directory '{base_directory}' and subdirectories for files to rename...")
    eligible_files = []
    
    for root, dirs, files in os.walk(base_directory):
        for filename in files:
            filepath = os.path.join(root, filename)
            
            # Ignore system/script files or .py/.url/.lnk files
            if filename.startswith('!-') or filename.lower().endswith(('.py', '.url', '.lnk')):
                continue
                
            eligible_files.append((filepath, root, filename))
        
    print(f"[+] Found {len(eligible_files)} eligible file(s) for renaming evaluation.\n")
    return eligible_files

def main():
    """
    Main execution function. Orchestrates the filtering and renaming
    of files within the script's directory and subfolders to remove time formats.
    """
    print("=" * 50)
    print("   Noterun Remove-Time (Subfolders) Rename Script Initialized")
    print("=" * 50)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    files_to_process = filter_eligible_files(script_dir)
    
    if not files_to_process:
        print("[*] No files to process. Exiting.")
        return 0
        
    print("-" * 50)
    
    success_count = 0
    failure_count = 0
    
    for filepath, directory, filename in files_to_process:
        if rename_file(filepath, directory, filename):
            success_count += 1
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
