# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import sys

def filter_eligible_files(directory: str) -> list:
    """
    Scans the directory for files that are eligible for modification time updates.
    
    Args:
        directory (str): The root directory to scan.
        
    Returns:
        list: A list of tuples (dirpath, filename).
    """
    print(f"[*] Scanning directory '{directory}' for files to update...")
    eligible_files = []
    
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        
        if not os.path.isfile(filepath):
            continue
            
        # Ignore system/script files, files starting with _, or .py/.url/.lnk files
        if filename.startswith('!-') or filename.startswith('_') or filename == os.path.basename(__file__) or filename.lower().endswith(('.py', '.url', '.lnk')):
            continue
            
        eligible_files.append((directory, filename))
        
    print(f"[+] Found {len(eligible_files)} eligible file(s) for updating.\n")
    return eligible_files

def update_file_time(filepath: str, filename: str) -> bool:
    """
    Updates the modification and access time for a single file.
    
    Args:
        filepath (str): The absolute path to the target file.
        filename (str): The name of the file.
        
    Returns:
        bool: True if updated successfully, False if an error occurred.
    """
    try:
        print(f"[*] Updating file...")
        print(f"    File: '{filepath}'")
        
        os.utime(filepath, None)
        print(f"[+] Successfully updated time for '{filename}'.\n")
        return True
        
    except PermissionError as e:
        print(f"[-] Permission Denied updating '{filepath}': {e}\n")
    except OSError as e:
        print(f"[-] OS Error updating '{filepath}': {e}\n")
    except Exception as e:
        print(f"[-] Unexpected error updating '{filepath}': {e}\n")
        
    return False

def main() -> int:
    """
    Main execution function. Orchestrates the filtering and modification time
    updates of files within the script's directory.
    """
    print("=" * 50)
    print("   Noterun Modification Time Update Script Initialized")
    print("=" * 50)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    files_to_process = filter_eligible_files(script_dir)
    
    if not files_to_process:
        print("[*] No files to process. Exiting.")
        return 0
        
    print("-" * 50)
    
    success_count = 0
    failure_count = 0
    
    for dirpath, filename in files_to_process:
        filepath = os.path.join(dirpath, filename)
        if update_file_time(filepath, filename):
            success_count += 1
        else:
            failure_count += 1
            
    print("-" * 50)
    print(f"[*] Update process completed.")
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
