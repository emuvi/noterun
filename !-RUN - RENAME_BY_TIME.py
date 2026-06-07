# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import datetime
import sys
from typing import Optional, Tuple

def get_file_time(filepath: str) -> Optional[datetime.datetime]:
    """
    Retrieves the file's creation time, falling back to modification time if necessary.
    
    Args:
        filepath (str): The absolute path to the file.
        
    Returns:
        datetime.datetime: The parsed datetime object, or None if an error occurs.
    """
    try:
        stat = os.stat(filepath)
        # On Windows, st_ctime is usually creation time.
        return datetime.datetime.fromtimestamp(stat.st_ctime)
    except AttributeError:
        return datetime.datetime.fromtimestamp(stat.st_mtime)
    except OSError as e:
        print(f"[-] OS Error getting file time for '{os.path.basename(filepath)}': {e}")
        return None
    except Exception as e:
        print(f"[-] Unexpected error getting file time for '{os.path.basename(filepath)}': {e}")
        return None

def parse_date_prefix(filename: str) -> Tuple[Optional[datetime.datetime], str, Optional[str]]:
    """
    Attempts to parse date/time prefix from the filename based on known formats.
    
    Args:
        filename (str): The name of the file to parse.
        
    Returns:
        tuple: (parsed_datetime, remaining_filename, matched_format_string)
               Returns (None, filename, None) if parsing fails.
    """
    formats = [
        "%Y.%m.%d_%H.%M.%S", "%Y-%m-%d_%H-%M-%S", "%Y.%m.%d %H.%M.%S",
        "%Y-%m-%d %H:%M:%S", "%Y.%m.%d-%H.%M.%S", "%Y.%m.%d",
        "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y",
        "%Y%m%d_%H%M%S", "%Y%m%d"
    ]
    
    # Check string prefixes from length 25 down to 8 characters
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

def generate_new_filename(filename: str, filepath: str) -> Optional[str]:
    """
    Generates the targeted standard filename using parsed or file system dates.
    
    Args:
        filename (str): The current name of the file.
        filepath (str): The absolute path to the file.
        
    Returns:
        str: The newly generated formatted filename, or None if no change is needed/possible.
    """
    dt, rest_of_name, fmt = parse_date_prefix(filename)
    target_fmt = "%Y.%m.%d_%H.%M.%S"

    if dt:
        # Skip if already perfectly formatted
        if fmt == target_fmt and filename.startswith(dt.strftime(target_fmt) + " - "):
            return None
            
        # If the recognized format lacks hour data, inject it from the file's metadata
        if fmt and '%H' not in fmt:
            file_dt = get_file_time(filepath)
            if file_dt:
                dt = dt.replace(hour=file_dt.hour, minute=file_dt.minute, second=file_dt.second)
    else:
        # No date recognized in string, rely purely on file metadata
        dt = get_file_time(filepath)
        if not dt:
            return None # Cannot process without a valid date
            
        rest_of_name = filename
        
        # Clean leading separators if any
        if rest_of_name.startswith(' - '):
            rest_of_name = rest_of_name[3:]
        elif rest_of_name.startswith('- ') or rest_of_name.startswith(' -'):
            rest_of_name = rest_of_name[2:]

    formatted_dt = dt.strftime(target_fmt)
    new_name = f"{formatted_dt} - {rest_of_name}"
    
    return new_name if new_name != filename else None

def get_safe_target_path(directory: str, filename: str) -> str:
    """
    Generates a unique file path within the given directory to avoid overwriting.
    
    Args:
        directory (str): The directory where the file will reside.
        filename (str): The desired filename.
        
    Returns:
        str: A safe, unique file path.
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
    Handles the date extraction and renaming operation for a single file.
    
    Args:
        filepath (str): The absolute path to the source file.
        directory (str): The directory of the file.
        filename (str): The current name of the file.
        
    Returns:
        bool: True if renamed or skipped intentionally, False if an error occurred.
    """
    try:
        new_name = generate_new_filename(filename, filepath)
        if not new_name:
            # File is already correctly named or couldn't be parsed
            return True

        new_filepath = get_safe_target_path(directory, new_name)
        final_name = os.path.basename(new_filepath)
        
        print(f"[*] Renaming file...")
        print(f"    From: '{filename}'")
        print(f"    To:   '{final_name}'")
        
        os.rename(filepath, new_filepath)
        print(f"[+] Successfully renamed '{filename}'.\n")
        return True
        
    except PermissionError as e:
        print(f"[-] Permission Denied renaming '{filename}': {e}\n")
    except OSError as e:
        print(f"[-] OS Error renaming '{filename}': {e}\n")
    except Exception as e:
        print(f"[-] Unexpected error renaming '{filename}': {e}\n")
        
    return False

def filter_eligible_files(directory: str) -> list:
    """
    Scans the directory for files that are eligible for renaming.
    
    Args:
        directory (str): The directory to scan.
        
    Returns:
        list: A list of eligible filenames.
    """
    print(f"[*] Scanning directory '{directory}' for files to rename...")
    eligible_files = []
    
    try:
        files = os.listdir(directory)
    except PermissionError as e:
        print(f"[-] Permission Denied accessing directory '{directory}': {e}")
        return []
    except Exception as e:
        print(f"[-] Unexpected error accessing directory '{directory}': {e}")
        return []

    for filename in files:
        filepath = os.path.join(directory, filename)
        
        if not os.path.isfile(filepath):
            continue
            
        # Ignore system/script files or .py/.url files
        if filename.startswith('!-') or filename == os.path.basename(__file__) or filename.lower().endswith(('.py', '.url')):
            continue
            
        eligible_files.append(filename)
        
    print(f"[+] Found {len(eligible_files)} eligible file(s) for renaming evaluation.\n")
    return eligible_files

def main():
    """
    Main execution function. Orchestrates the filtering and date-based renaming
    of files within the script's directory.
    """
    print("=" * 50)
    print("   Noterun Date-Based Rename Script Initialized")
    print("=" * 50)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    files_to_process = filter_eligible_files(script_dir)
    
    if not files_to_process:
        print("[*] No files to process. Exiting.")
        return 0
        
    print("-" * 50)
    
    success_count = 0
    failure_count = 0
    
    for filename in files_to_process:
        filepath = os.path.join(script_dir, filename)
        if rename_file(filepath, script_dir, filename):
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
