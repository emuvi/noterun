# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import re
import sys
import time
import datetime
from typing import Optional, Tuple, List

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def print_error(message: str) -> None:
    """Prints an error message to stderr."""
    print(message, file=sys.stderr)

def get_current_time() -> str:
    """
    Returns the current local time formatted as [HH:MM:SS].
    
    Returns:
        str: The formatted timestamp.
    """
    return time.strftime("[%H:%M:%S]")

def _extract_rest_if_valid_boundary(filename: str, length: int, fmt: str) -> Optional[str]:
    rest = filename[length:]
    if not rest:
        return "" if fmt != "%Y" else None

    _, ext = os.path.splitext(filename)
    has_real_ext = bool(ext and re.match(r"^\.[A-Za-z0-9]{1,10}$", ext) and not ext[1:].isdigit())

    for separator, sep_len in ((' - ', 3), ('- ', 2), (' -', 2), (' ', 1), ('-', 1), ('_', 1)):
        if rest.startswith(separator):
            if fmt == "%Y":
                if separator == ' ':
                    return None
                after = rest[sep_len:]
                if not after or (has_real_ext and after == ext):
                    return None
            return rest[sep_len:]

    if has_real_ext and rest == ext and fmt != "%Y":
        return rest

    if length >= 8 and fmt != "%Y" and rest[0].isalpha():
        return rest

    return None


def parse_date_prefix(filename: str) -> Tuple[Optional[datetime.datetime], str, Optional[str]]:
    """
    Attempts to parse a date/time prefix from the filename based on known full and partial formats.
    """
    english_months = (
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    )
    english_patterns = (
        (r"^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\s+(\d{2})-(\d{2})-(\d{2})", "%B %d %Y %H-%M-%S"),
        (r"^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\s+(\d{2})-(\d{2})", "%B %d %Y %H-%M"),
        (r"^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", "%B %d %Y"),
        (r"^([A-Za-z]+)\s+(\d{4})", "%B %Y"),
    )
    for pat, eng_fmt in english_patterns:
        m = re.match(pat, filename, re.IGNORECASE)
        if not m:
            continue
        month_name = m.group(1).casefold()
        if month_name not in english_months:
            continue
        month = english_months.index(month_name) + 1
        rest_candidate = _extract_rest_if_valid_boundary(filename, m.end(), eng_fmt)
        if rest_candidate is None:
            continue
        try:
            if eng_fmt == "%B %d %Y %H-%M-%S":
                day, year, hour, minute, second = map(int, m.groups()[1:])
                dt = datetime.datetime(year, month, day, hour, minute, second)
            elif eng_fmt == "%B %d %Y %H-%M":
                day, year, hour, minute = map(int, m.groups()[1:])
                dt = datetime.datetime(year, month, day, hour, minute)
            elif eng_fmt == "%B %d %Y":
                day, year = map(int, m.groups()[1:])
                dt = datetime.datetime(year, month, day)
            else:
                year = int(m.group(2))
                dt = datetime.datetime(year, month, 1)
            if 1900 <= dt.year <= 2100:
                return dt, rest_candidate, eng_fmt
        except ValueError:
            continue

    formats = [
        "%Y.%m.%d-%H.%M.%S", "%Y.%m.%d_%H.%M.%S", "%Y.%m.%d %H.%M.%S",
        "%Y-%m-%d-%H-%M-%S", "%Y-%m-%d_%H-%M-%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H-%M-%S",
        "%Y-%m-%d-%H.%M.%S", "%Y-%m-%d_%H.%M.%S", "%Y-%m-%d %H.%M.%S",
        "%d.%m.%Y-%H.%M.%S", "%d-%m-%Y-%H.%M.%S", "%d-%m-%Y_%H-%M.%S",
        "%Y%m%d_%H%M%S", "%Y%m%d-%H%M%S", "%y%m%d_%H%M%S", "%y%m%d-%H%M%S", "%Y%m%d%H%M%S",
        "%Y.%m.%d-%H.%M", "%Y.%m.%d_%H.%M", "%Y.%m.%d %H.%M",
        "%Y-%m-%d-%H-%M", "%Y-%m-%d_%H-%M", "%Y-%m-%d %H-%M",
        "%Y-%m-%d-%H.%M", "%Y-%m-%d_%H.%M", "%Y-%m-%d %H.%M",
        "%d.%m.%Y-%H.%M", "%d-%m-%Y-%H.%M", "%d-%m-%Y_%H.%M",
        "%Y%m%d_%H%M", "%Y%m%d-%H%M", "%y%m%d_%H%M", "%y%m%d-%H%M", "%Y%m%d%H%M",
        "%Y.%m.%d-%H", "%Y.%m.%d_%H",
        "%Y-%m-%d-%H", "%Y-%m-%d_%H",
        "%d.%m.%Y-%H", "%d-%m-%Y-%H",
        "%Y%m%d_%H", "%Y%m%d-%H",
        "%Y.%m.%d", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d",
        "%Y.%m", "%Y-%m", "%m.%Y", "%m-%Y",
    ]
    
    for length in range(25, 5, -1):
        if length > len(filename):
            continue
        prefix = filename[:length]
        for fmt in formats:
            try:
                dt = datetime.datetime.strptime(prefix, fmt)
                if not (1900 <= dt.year <= 2100):
                    continue
                if any(c in fmt for c in ("%Y%m", "%y%m", "%m%d", "%H%M", "%M%S")) and dt.strftime(fmt) != prefix:
                    continue
                rest_candidate = _extract_rest_if_valid_boundary(filename, length, fmt)
                if rest_candidate is not None:
                    return dt, rest_candidate, fmt
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
    match = re.match(r"^(\[ .*? \] - )(.*)$", filename)
    if match:
        prefix_part = match.group(1)
        name_to_parse = match.group(2)
    else:
        prefix_part = ""
        name_to_parse = filename
        
    _, ext = os.path.splitext(name_to_parse)
    dt, rest_part, fmt = parse_date_prefix(name_to_parse)
    if dt:
        if not rest_part or (ext and rest_part == ext):
            return None, "Removing time would leave file without name/extension"
        return f"{prefix_part}{rest_part}", None
        
    return None, "No matching time format found in filename"

def get_safe_target_path(directory: str, filename: str) -> str:
    """
    Generates a unique file path within the given directory to avoid overwriting.
    
    Args:
        directory (str): The destination directory path.
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
    Handles the operation to remove time from a single file's name.
    
    Args:
        filepath (str): The full path to the current file.
        directory (str): The directory containing the file.
        filename (str): The current name of the file.
        
    Returns:
        bool: True if operation was successful or file was cleanly skipped, False on error.
    """
    print(f"{get_current_time()} 🔹 [STEP] [rename_file] Starting - filepath: '{filepath}'")
    try:
        new_name, skip_reason = remove_time_from_filename(filename)
        if not new_name:
            print(f"{get_current_time()} ℹ️ [LOG] Skipping file '{filename}' - Reason: {skip_reason}")
            print(f"{get_current_time()} ✅ [SUCCESS] [rename_file] Completed gracefully without changes")
            return True

        last_error = None
        for attempt in range(1, 4):
            try:
                new_filepath = get_safe_target_path(directory, new_name)
                final_name = os.path.basename(new_filepath)
                if attempt == 1:
                    print(f"{get_current_time()} ℹ️ [LOG] Renaming file from '{filename}' to '{final_name}'")
                os.rename(filepath, new_filepath)
                print(f"{get_current_time()} ✅ [SUCCESS] [rename_file] Successfully renamed '{filename}' to '{final_name}'")
                return True
            except PermissionError as e:
                last_error = f"Permission Denied renaming '{filename}': {e}. Fix: Check if the file is open in another program and ensure you have write permissions."
                if attempt < 3:
                    time.sleep(0.4 * attempt)
                    continue
            except OSError as e:
                last_error = f"OS Error renaming '{filename}': {e}. Fix: Verify path validity and disk space."
                if attempt < 3:
                    time.sleep(0.4 * attempt)
                    continue

        print_error(f"{get_current_time()} 🔴 [ERROR] [rename_file] {last_error}")
        return False
    except Exception as e:
        print_error(f"{get_current_time()} 🔴 [ERROR] [rename_file] Unexpected error renaming '{filename}': {e}. Fix: Check logs for further details.")
        return False

def filter_eligible_files(base_directory: str) -> Tuple[List[Tuple[str, str, str]], int]:
    """
    Scans the directory and subdirectories for files that are eligible for renaming.
    """
    print(f"{get_current_time()} 🔹 [STEP] [filter_eligible_files] Starting - base_directory: '{base_directory}'")
    eligible_files = []
    scan_errors = [0]

    def _on_walk_error(err: OSError) -> None:
        scan_errors[0] += 1
        print_error(f"{get_current_time()} 🔴 [ERROR] [filter_eligible_files] Error accessing folder: {err}")

    self_name = os.path.basename(__file__)
    self_bat = os.path.splitext(self_name)[0] + ".bat"

    for root, dirs, files in os.walk(base_directory, onerror=_on_walk_error):
        for filename in files:
            filepath = os.path.join(root, filename)
            
            # Ignore system/script files or .py/.url/.lnk files
            if filename.startswith('!-') or filename in (self_name, self_bat) or filename.lower().endswith(('.py', '.url', '.lnk')):
                continue
                
            eligible_files.append((filepath, root, filename))
        
    print(f"{get_current_time()} ✅ [SUCCESS] [filter_eligible_files] Found {len(eligible_files)} eligible file(s) for renaming evaluation")
    return eligible_files, scan_errors[0]

def print_summary_box(total: int, successes: int, failures: int) -> None:
    """
    Prints a visual summary box with Unicode drawing characters showing the final results.
    
    Args:
        total (int): Total number of files processed.
        successes (int): Total number of successfully renamed files.
        failures (int): Total number of failures during renaming.
    """
    print(f"\n{get_current_time()} 🔹 [STEP] [print_summary_box] Starting summary display")
    print("╔═══════════════════════════════════════════════╗")
    print("║          Processing Summary                   ║")
    print("╠═══════════════════════════════════════════════╣")
    print(f"║ Total Processed: {total:<29}║")
    print(f"║ Successes:       {successes:<29}║")
    print(f"║ Failures:        {failures:<29}║")
    print("╚═══════════════════════════════════════════════╝")
    print(f"{get_current_time()} ✅ [SUCCESS] [print_summary_box] Summary display completed\n")

def main() -> int:
    """
    Main execution function. Orchestrates the filtering and renaming
    of files within the script's directory and subfolders to remove time formats.
    
    Returns:
        int: Exit code (0 for success, 1 for errors).
    """
    print("=" * 50)
    print(f"{get_current_time()} 🔹 [STEP] [main] Noterun Remove-Time (Subfolders) Rename Script Initialized")
    print("=" * 50)
    
    script_dir = os.getcwd()
    files_to_process, scan_errors = filter_eligible_files(script_dir)
    
    if not files_to_process:
        print(f"{get_current_time()} ℹ️ [LOG] No eligible files to process. Exiting.")
        return 1 if scan_errors > 0 else 0
        
    print("-" * 50)
    
    success_count = 0
    failure_count = scan_errors
    total_files = len(files_to_process)
    
    for i, (filepath, directory, filename) in enumerate(files_to_process, 1):
        print(f"{get_current_time()} 🔹 [STEP] [rename_cycle] Processing item {i} of {total_files}")
        print(f"{get_current_time()} ℹ️ [LOG] Processing: '{filename}' in directory '{directory}'")
        if rename_file(filepath, directory, filename):
            success_count += 1
        else:
            failure_count += 1
            
    print("-" * 50)
    print(f"{get_current_time()} ✅ [SUCCESS] [main] Renaming process completed")
    
    print_summary_box(total_files, success_count, failure_count)
    
    if failure_count > 0:
        print_error(f"{get_current_time()} 🔴 [ERROR] [main] Completed with {failure_count} errors")
        return 1
    else:
        print(f"{get_current_time()} ✅ [SUCCESS] [main] All files processed without errors!")
        return 0

if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[*] Process interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print_error(f"{get_current_time()} 🔴 [ERROR] [main] Fatal error: {e}")
        sys.exit(1)
