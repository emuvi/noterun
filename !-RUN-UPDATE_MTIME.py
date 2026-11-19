# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import stat
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


def filter_eligible_files(directory: str) -> tuple:
    """
    Scans the directory for files that are eligible for modification time updates.
    
    Args:
        directory (str): The root directory to scan.
        
    Returns:
        tuple: (list of tuples (dirpath, filename), bool scan_ok).
    """
    print(f"[*] Scanning directory '{directory}' for files to update...")
    eligible_files = []

    try:
        entries = os.listdir(directory)
    except PermissionError as e:
        print_error(f"[-] Permission Denied accessing directory '{directory}': {e}")
        return [], False
    except Exception as e:
        print_error(f"[-] Unexpected error accessing directory '{directory}': {e}")
        return [], False

    self_name = os.path.basename(__file__)
    self_bat = os.path.splitext(self_name)[0] + ".bat"

    for filename in entries:
        filepath = os.path.join(directory, filename)
        
        try:
            if not os.path.isfile(filepath):
                continue
        except OSError:
            continue
            
        # Ignore system/script files, files starting with _, or .py/.url/.lnk files
        if filename.startswith('!-') or filename.startswith('_') or filename in (self_name, self_bat) or filename.lower().endswith(('.py', '.url', '.lnk')):
            continue
            
        eligible_files.append((directory, filename))
        
    print(f"[+] Found {len(eligible_files)} eligible file(s) for updating.\n")
    return eligible_files, True

def update_file_time(filepath: str, filename: str) -> bool:
    """
    Updates the modification and access time for a single file.
    
    Args:
        filepath (str): The absolute path to the target file.
        filename (str): The name of the file.
        
    Returns:
        bool: True if updated successfully, False if an error occurred.
    """
    print(f"[*] Updating file...")
    print(f"    File: '{filepath}'")
    last_error = None

    for attempt in range(1, 4):
        try:
            os.utime(filepath, None)
            print(f"[+] Successfully updated time for '{filename}'.\n")
            return True
        except PermissionError as e:
            last_error = f"Permission Denied updating '{filepath}': {e}"
            # Workaround: file might have read-only flag on Windows
            try:
                os.chmod(filepath, stat.S_IWRITE | stat.S_IREAD)
                os.utime(filepath, None)
                print(f"[+] Successfully updated time for '{filename}' (cleared read-only attribute).\n")
                return True
            except OSError:
                pass
            if attempt < 3:
                time.sleep(0.4 * attempt)
                continue
        except OSError as e:
            last_error = f"OS Error updating '{filepath}': {e}"
            if attempt < 3:
                time.sleep(0.4 * attempt)
                continue
        except Exception as e:
            last_error = f"Unexpected error updating '{filepath}': {e}"
            break

    print_error(f"[-] {last_error}\n")
    return False

def main() -> int:
    """
    Main execution function. Orchestrates the filtering and modification time
    updates of files within the script's directory.
    """
    print("=" * 50)
    print("   Noterun Modification Time Update Script Initialized")
    print("=" * 50)
    
    script_dir = os.getcwd()
    files_to_process, scan_ok = filter_eligible_files(script_dir)
    if not scan_ok:
        return 1
    
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
        print_error(f"[-] Errors encountered: {failure_count}")
        return 1
    else:
        print("[+] All files processed without errors!")
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
