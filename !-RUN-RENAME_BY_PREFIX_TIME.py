# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import calendar
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


def read_input(prompt: str = "") -> str:
    """
    Prints the prompt to stdout and reads a line from stdin without writing to stderr.
    Avoids CPython's interactive input(prompt) writing prompts to stderr on Windows consoles.
    """
    if prompt:
        print(prompt, end="", flush=True)
    line = sys.stdin.readline()
    if line == "":
        raise EOFError
    return line.rstrip("\r\n")


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

def _extract_rest_if_valid_boundary(filename: str, length: int, fmt: str) -> Optional[str]:
    """
    Verifies that filename[:length] ends on a valid separator or extension boundary
    and returns the remaining filename with any leading separator stripped.
    """
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


def needs_datetime_completion(fmt: Optional[str]) -> bool:
    """Returns True if any date/time component (month, day, hour, minute, second) is missing from fmt."""
    if not fmt:
        return True
    has_month = any(tok in fmt for tok in ("%m", "%B", "%b"))
    has_hour = any(tok in fmt for tok in ("%H", "%I"))
    return not (has_month and "%d" in fmt and has_hour and "%M" in fmt and "%S" in fmt)


def complete_datetime_from_file(
    dt: datetime.datetime,
    fmt: Optional[str],
    file_dt: datetime.datetime,
) -> datetime.datetime:
    """
    Completes only the missing date/time components in `dt` (according to `fmt`)
    using the file's modification timestamp `file_dt`.
    """
    if not fmt:
        return file_dt

    year = dt.year
    has_month = any(tok in fmt for tok in ("%m", "%B", "%b"))
    month = dt.month if has_month else file_dt.month

    if "%d" in fmt:
        day = dt.day
    else:
        max_day = calendar.monthrange(year, month)[1]
        day = min(file_dt.day, max_day)

    has_hour = any(tok in fmt for tok in ("%H", "%I"))
    hour = dt.hour if has_hour else file_dt.hour
    minute = dt.minute if "%M" in fmt else file_dt.minute
    second = dt.second if "%S" in fmt else file_dt.second

    return datetime.datetime(year, month, day, hour, minute, second)


def parse_date_prefix(filename: str) -> Tuple[Optional[datetime.datetime], str, Optional[str]]:
    """
    Attempts to parse date/time prefix from the filename based on known full and partial formats.
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
        "%Y",
    ]
    
    # Check string prefixes from length 25 down to 4 characters
    for length in range(25, 3, -1):
        if length > len(filename):
            continue
        prefix = filename[:length]
        for fmt in formats:
            if fmt == "%Y" and not (length == 4 and prefix.isdigit()):
                continue
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

def is_already_prefixed_time(filename: str) -> bool:
    """
    Checks if the filename is already prefixed with a time format (including seconds), regardless of the prefix string.
    """
    pattern = r"^\[ .*? \] - \d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}(?: - |\.[A-Za-z0-9]{1,10}$|$)"
    return bool(re.match(pattern, filename))

def generate_new_filename(filename: str, filepath: str, user_prefix: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Generates the targeted standard filename using user prefix and parsed/metadata dates.
    """
    if is_already_prefixed_time(filename):
        return None, "Already prefixed by a previous time-based rename operation"

    existing_prefix_match = re.match(r"^(\[ .*? \] - )(.*)$", filename)
    if existing_prefix_match:
        prefix_str = existing_prefix_match.group(1)
        name_to_parse = existing_prefix_match.group(2)
    else:
        prefix_str = f"[ {user_prefix} ] - "
        name_to_parse = filename

    dt, rest_of_name, fmt = parse_date_prefix(name_to_parse)
    target_fmt = "%Y.%m.%d-%H.%M.%S"
    _, name_ext = os.path.splitext(name_to_parse)
    has_real_ext = bool(name_ext and re.match(r"^\.[A-Za-z0-9]{1,10}$", name_ext) and not name_ext[1:].isdigit())

    if dt:
        if needs_datetime_completion(fmt):
            file_dt = get_file_time(filepath)
            if not file_dt:
                return None, "Cannot process without a valid date in file metadata"
            dt = complete_datetime_from_file(dt, fmt, file_dt)
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
    if dt and ((has_real_ext and rest_of_name == name_ext) or rest_of_name == ""):
        new_name = f"{prefix_str}{formatted_dt}{rest_of_name}"
    else:
        new_name = f"{prefix_str}{formatted_dt} - {rest_of_name}"
    
    if new_name == filename:
        return None, f"Already perfectly formatted with prefix '{prefix_str}' and date"
        
    return new_name, None

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

def rename_file(filepath: str, directory: str, filename: str, user_prefix: str) -> bool:
    """
    Handles the date extraction and renaming operation for a single file.
    """
    try:
        new_name, skip_reason = generate_new_filename(filename, filepath, user_prefix)
        if not new_name:
            print(f"[*] Skipping file...")
            print(f"    File: '{filename}'")
            print(f"    Reason: {skip_reason}\n")
            return True

        last_error = None
        for attempt in range(1, 4):
            try:
                new_filepath = get_safe_target_path(directory, new_name)
                final_name = os.path.basename(new_filepath)
                if attempt == 1:
                    print(f"[*] Renaming file...")
                    print(f"    From: '{filename}'")
                    print(f"    To:   '{final_name}'")
                os.rename(filepath, new_filepath)
                print(f"[+] Successfully renamed '{filename}'.\n")
                return True
            except PermissionError as e:
                last_error = f"Permission Denied renaming '{filename}': {e}"
                if attempt < 3:
                    time.sleep(0.4 * attempt)
                    continue
            except OSError as e:
                last_error = f"OS Error renaming '{filename}': {e}"
                if attempt < 3:
                    time.sleep(0.4 * attempt)
                    continue

        print_error(f"[-] {last_error}\n")
        return False
    except Exception as e:
        print_error(f"[-] Unexpected error renaming '{filename}': {e}\n")
        return False

def filter_eligible_files(directory: str) -> tuple:
    """
    Scans the directory for files that are eligible for renaming.
    """
    print(f"[*] Scanning directory '{directory}' for files to rename...")
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
        
        try:
            if not os.path.isfile(filepath):
                continue
        except OSError:
            continue
            
        # Ignore system/script files, files starting with _, or .py/.url/.lnk files
        if filename.startswith('!-') or filename.startswith('_') or filename in (self_name, self_bat) or filename.lower().endswith(('.py', '.url', '.lnk')):
            continue
            
        eligible_files.append(filename)
        
    print(f"[+] Found {len(eligible_files)} eligible file(s) for renaming evaluation.\n")
    return eligible_files, True

def main():
    """
    Main execution function. Orchestrates the filtering and prefix-date-based renaming
    of files within the script's directory.
    """
    print("=" * 50)
    print("   Noterun Prefix-Time Rename Script Initialized")
    print("=" * 50)
    
    try:
        user_prefix = read_input("Enter the string to use as prefix: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n[*] Operation canceled by user.")
        return 0

    user_prefix = re.sub(r'[\\/*?:"<>|]', '', user_prefix).strip()
    if not user_prefix:
        print("[*] No valid prefix entered. Exiting.")
        return 0

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
    
    for filename in files_to_process:
        filepath = os.path.join(script_dir, filename)
        if rename_file(filepath, script_dir, filename, user_prefix):
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