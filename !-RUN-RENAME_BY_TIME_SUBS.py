# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import datetime
import sys
import re
import time
from typing import Optional, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def print_error(message: str) -> None:
    """Prints an error message to stderr."""
    print(message, file=sys.stderr)


def get_file_time(filepath: str) -> Optional[datetime.datetime]:
    """
    Retrieves the file's modification time, falling back safely if timestamps are invalid.
    """
    try:
        stat = os.stat(filepath)
    except OSError as e:
        print_error(f"[-] OS Error getting file time for '{os.path.basename(filepath)}': {e}")
        return None
    except Exception as e:
        print_error(f"[-] Unexpected error getting file time for '{os.path.basename(filepath)}': {e}")
        return None

    for ts_attr in ("st_mtime", "st_ctime"):
        ts = getattr(stat, ts_attr, None)
        if ts is not None:
            try:
                return datetime.datetime.fromtimestamp(ts)
            except (OSError, OverflowError, ValueError):
                continue
    return datetime.datetime.now()

def parse_date_prefix(filename: str) -> Tuple[Optional[datetime.datetime], str, Optional[str]]:
    """
    Attempts to parse date/time prefix from the filename based on known formats.
    
    Args:
        filename (str): The name of the file to parse.
        
    Returns:
        tuple: (parsed_datetime, remaining_filename, matched_format_string)
               Returns (None, filename, None) if parsing fails.
    """
    english_months = (
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    )
    english_timestamp = re.match(
        r"^([A-Za-z]+)\s+(\d{1,2})\s+(\d{4})\s+(\d{2})-(\d{2})-(\d{2})",
        filename, re.IGNORECASE,
    )
    if english_timestamp:
        try:
            month = english_months.index(english_timestamp.group(1).casefold()) + 1
            day, year, hour, minute, second = map(int, english_timestamp.groups()[1:])
            dt = datetime.datetime(year, month, day, hour, minute, second)
        except ValueError:
            pass
        else:
            rest = filename[english_timestamp.end():]
            for separator, length in ((' - ', 3), ('- ', 2), (' -', 2), (' ', 1), ('-', 1), ('_', 1)):
                if rest.startswith(separator):
                    rest = rest[length:]
                    break
            return dt, rest, "%B %d %Y %H-%M-%S"

    formats = [
        "%Y.%m.%d-%H.%M.%S", "%Y.%m.%d-%H.%M", "%Y.%m.%d_%H.%M.%S", "%Y-%m-%d_%H-%M-%S",
        "%Y.%m.%d %H.%M.%S", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d",
        "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y",
        "%y%m%d_%H%M%S", "%Y%m%d_%H%M%S", "%Y%m%d",
        "%Y.%m.%d %H.%M", "%Y-%m-%d %H.%M", "%Y-%m-%d_%H.%M",
        "%Y%m%d%H%M%S", "%Y%m%d%H%M"
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

def generate_new_filename(filename: str, filepath: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Generates the targeted standard filename using parsed or file system dates.
    
    Args:
        filename (str): The current name of the file.
        filepath (str): The absolute path to the file.
        
    Returns:
        tuple: (new_name, skip_reason). The newly generated formatted filename, or None if no change is needed/possible.
    """
    prefix_match = re.match(r"^(\[ .*? \] - )(.*)$", filename)
    if prefix_match:
        existing_prefix = prefix_match.group(1)
        name_to_parse = prefix_match.group(2)
    else:
        existing_prefix = ""
        name_to_parse = filename

    dt, rest_of_name, fmt = parse_date_prefix(name_to_parse)
    target_fmt = "%Y.%m.%d-%H.%M.%S"

    if dt:
        # Skip if already perfectly formatted
        if fmt == target_fmt and name_to_parse.startswith(dt.strftime(target_fmt) + " - "):
            return None, "Already perfectly formatted with date prefix"
            
        # If the recognized format lacks hour or second data, inject missing parts from the file's metadata
        if fmt and '%H' not in fmt:
            file_dt = get_file_time(filepath)
            if not file_dt:
                return None, "Cannot process without a valid date in file metadata"
            dt = dt.replace(hour=file_dt.hour, minute=file_dt.minute, second=file_dt.second)
        elif fmt and '%S' not in fmt:
            file_dt = get_file_time(filepath)
            if not file_dt:
                return None, "Cannot process without a valid date in file metadata"
            dt = dt.replace(second=file_dt.second)
    else:
        # No date recognized in string, rely purely on file metadata
        dt = get_file_time(filepath)
        if not dt:
            return None, "Cannot process without a valid date in file metadata"
            
        rest_of_name = name_to_parse
        
        # Clean leading separators if any
        if rest_of_name.startswith(' - '):
            rest_of_name = rest_of_name[3:]
        elif rest_of_name.startswith('- ') or rest_of_name.startswith(' -'):
            rest_of_name = rest_of_name[2:]

    formatted_dt = dt.strftime(target_fmt)
    new_name = f"{existing_prefix}{formatted_dt} - {rest_of_name}"
    
    if new_name == filename:
        return None, "Already perfectly formatted with date prefix"
        
    return new_name, None

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
        new_name, skip_reason = generate_new_filename(filename, filepath)
        if not new_name:
            # File is already correctly named or couldn't be parsed
            print(f"[*] Skipping file...")
            print(f"    File: '{filepath}'")
            print(f"    Reason: {skip_reason}\n")
            return True

        last_error = None
        for attempt in range(1, 4):
            try:
                new_filepath = get_safe_target_path(directory, new_name)
                final_name = os.path.basename(new_filepath)
                if attempt == 1:
                    print(f"[*] Renaming file...")
                    print(f"    From: '{filepath}'")
                    print(f"    To:   '{new_filepath}'")
                os.rename(filepath, new_filepath)
                print(f"[+] Successfully renamed '{filename}' to '{final_name}'.\n")
                return True
            except PermissionError as e:
                last_error = f"Permission Denied renaming '{filepath}': {e}"
                if attempt < 3:
                    time.sleep(0.4 * attempt)
                    continue
            except OSError as e:
                last_error = f"OS Error renaming '{filepath}': {e}"
                if attempt < 3:
                    time.sleep(0.4 * attempt)
                    continue

        print_error(f"[-] {last_error}\n")
        return False
    except Exception as e:
        print_error(f"[-] Unexpected error renaming '{filepath}': {e}\n")
        return False

def filter_eligible_files(directory: str) -> tuple:
    """
    Scans the directory and subfolders for files that are eligible for renaming.
    """
    print(f"[*] Scanning directory '{directory}' and subfolders for files to rename...")
    eligible_files = []
    scan_errors = [0]

    def _on_walk_error(err: OSError) -> None:
        scan_errors[0] += 1
        print_error(f"[-] Error accessing folder during scan: {err}")

    self_name = os.path.basename(__file__)
    self_bat = os.path.splitext(self_name)[0] + ".bat"

    for dirpath, dirnames, filenames in os.walk(directory, onerror=_on_walk_error):
        for filename in filenames:
            # Ignore system/script files, files starting with _, or .py/.url/.lnk files
            if filename.startswith('!-') or filename.startswith('_') or filename in (self_name, self_bat) or filename.lower().endswith(('.py', '.url', '.lnk')):
                continue
                
            eligible_files.append((dirpath, filename))
        
    print(f"[+] Found {len(eligible_files)} eligible file(s) for renaming evaluation.\n")
    return eligible_files, scan_errors[0]

def main():
    """
    Main execution function. Orchestrates the filtering and date-based renaming
    of files within the script's directory and its subfolders.
    """
    print("=" * 50)
    print("   Noterun Date-Based Rename Script (Recursive) Initialized")
    print("=" * 50)
    
    script_dir = os.getcwd()
    files_to_process, scan_errors = filter_eligible_files(script_dir)
    
    if not files_to_process:
        print("[*] No files to process. Exiting.")
        return 1 if scan_errors > 0 else 0
        
    print("-" * 50)
    
    success_count = 0
    failure_count = scan_errors
    
    for dirpath, filename in files_to_process:
        filepath = os.path.join(dirpath, filename)
        if rename_file(filepath, dirpath, filename):
            success_count += 1
        else:
            failure_count += 1
            
    print("-" * 50)
    print(f"[*] Renaming process completed.")
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
