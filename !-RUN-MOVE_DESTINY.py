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

DESTINY_FILENAME = "!-RUN-MOVE_DESTINY.txt"


def print_error(message: str) -> None:
    """Prints an error message to stderr."""
    print(message, file=sys.stderr)


def find_destiny_file(script_dir: str) -> tuple:
    """
    Locates the destinations list file in the current directory or next to the script.

    Args:
        script_dir (str): The current working directory.

    Returns:
        tuple: (path to the destinations file or None, list of searched paths)
    """
    cwd_path = os.path.join(script_dir, DESTINY_FILENAME)
    searched = [cwd_path]

    if os.path.isfile(cwd_path):
        return cwd_path, searched

    script_home = os.path.dirname(os.path.abspath(__file__))
    home_path = os.path.join(script_home, DESTINY_FILENAME)
    if os.path.normcase(os.path.abspath(home_path)) != os.path.normcase(os.path.abspath(cwd_path)):
        searched.append(home_path)
        if os.path.isfile(home_path):
            return home_path, searched

    return None, searched


def parse_destiny_line(raw_line: str, base_dir: str):
    """
    Parses a single line from the destinations file.
    Supports blank lines, comments starting with '#' or ';', optional 'Label | Path'
    syntax, surrounding quotes, environment variables, '~', and relative paths.

    Args:
        raw_line (str): Raw line read from the destinations file.
        base_dir (str): Base directory for resolving relative paths.

    Returns:
        tuple or None: (label_or_none, resolved_absolute_path), or None if ignored.
    """
    line = raw_line.strip()
    if not line or line.startswith("#") or line.startswith(";"):
        return None

    label = None
    path_part = line

    if "|" in line:
        left, right = line.split("|", 1)
        left = left.strip()
        right = right.strip()
        if right:
            label = left or None
            path_part = right

    if len(path_part) >= 2 and path_part[0] == path_part[-1] and path_part[0] in ('"', "'"):
        path_part = path_part[1:-1].strip()

    if not path_part:
        return None

    expanded = os.path.expanduser(os.path.expandvars(path_part))
    if not os.path.isabs(expanded):
        resolved = os.path.abspath(os.path.join(base_dir, expanded))
    else:
        resolved = os.path.abspath(os.path.normpath(expanded))

    return label, resolved


def load_destinations(destiny_file: str, base_dir: str) -> tuple:
    """
    Reads and parses destination directories from the destinations file.

    Args:
        destiny_file (str): Absolute path to the destinations text file.
        base_dir (str): Base directory for resolving relative paths.

    Returns:
        tuple: (list of (label, path) tuples, bool indicating whether reading succeeded)
    """
    lines = None
    last_error = None

    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with open(destiny_file, "r", encoding=encoding) as f:
                lines = f.readlines()
            break
        except UnicodeDecodeError as e:
            last_error = f"Encoding error reading '{destiny_file}': {e}"
            continue
        except PermissionError as e:
            print_error(f"[-] Permission Denied reading '{destiny_file}': {e}")
            return [], False
        except OSError as e:
            print_error(f"[-] OS Error reading '{destiny_file}': {e}")
            return [], False
        except Exception as e:
            print_error(f"[-] Unexpected error reading '{destiny_file}': {e}")
            return [], False

    if lines is None:
        print_error(f"[-] {last_error or f'Unable to read {destiny_file}'}")
        return [], False

    destinations = []
    seen = set()

    for raw_line in lines:
        parsed = parse_destiny_line(raw_line, base_dir)
        if parsed is None:
            continue
        label, resolved_path = parsed
        key = os.path.normcase(resolved_path)
        if key in seen:
            continue
        seen.add(key)
        destinations.append((label, resolved_path))

    return destinations, True


def display_destinations(destinations: list, current_dir: str) -> None:
    """
    Prints the numbered list of available destination directories.

    Args:
        destinations (list): List of (label, path) tuples.
        current_dir (str): The current working directory.
    """
    current_dir_norm = os.path.normcase(os.path.abspath(current_dir))
    width = len(str(len(destinations)))

    print("[*] Available destinations:")
    for idx, (label, path) in enumerate(destinations, start=1):
        status_tags = []
        path_norm = os.path.normcase(os.path.abspath(path))
        if path_norm == current_dir_norm:
            status_tags.append("current directory")
        elif os.path.isfile(path):
            status_tags.append("not a directory")
        elif not os.path.isdir(path):
            status_tags.append("not found")

        suffix = f" [{' / '.join(status_tags)}]" if status_tags else ""
        if label:
            print(f"  [{idx:>{width}}] {label} -> {path}{suffix}")
        else:
            print(f"  [{idx:>{width}}] {path}{suffix}")
    print(f"  [{'0':>{width}}] Cancel / Exit")


def choose_destination(destinations: list, current_dir: str) -> tuple:
    """
    Prompts the user to select a destination directory from the configured list.

    Args:
        destinations (list): List of (label, path) tuples.
        current_dir (str): The current working directory.

    Returns:
        tuple: (selected directory path or None, bool indicating if a fatal error occurred)
    """
    current_dir_norm = os.path.normcase(os.path.abspath(current_dir))
    display_destinations(destinations, current_dir)

    while True:
        try:
            choice = input(
                f"\nSelect destination [1-{len(destinations)}] (0 or Enter to cancel): "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[*] Operation canceled by user.")
            return None, False

        if not choice or choice.lower() in ("0", "q", "quit", "exit", "cancel", "s", "sair"):
            print("[*] Operation canceled by user.")
            return None, False

        if not (choice.isascii() and choice.isdigit()):
            print(
                f"[!] Invalid option '{choice}'. Enter a number between 1 and {len(destinations)}, or 0 to cancel."
            )
            continue

        index = int(choice)
        if index < 1 or index > len(destinations):
            print(
                f"[!] Option {index} is out of range. Enter a number between 1 and {len(destinations)}, or 0 to cancel."
            )
            continue

        _, target_dir = destinations[index - 1]
        target_norm = os.path.normcase(os.path.abspath(target_dir))

        if target_norm == current_dir_norm:
            print(f"[!] Destination '{target_dir}' is the current directory. Please choose another.")
            continue

        if os.path.isfile(target_dir):
            print(f"[!] Destination '{target_dir}' is a file, not a directory. Please choose another.")
            continue

        if not os.path.isdir(target_dir):
            print(f"[!] Destination directory does not exist: {target_dir}")
            try:
                create_ans = input("    Do you want to create this directory? (Y/N): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n[*] Operation canceled by user.")
                return None, False

            if create_ans in ("y", "yes", "s", "sim"):
                try:
                    os.makedirs(target_dir, exist_ok=True)
                    print(f"[+] Created destination directory: {target_dir}\n")
                except OSError as e:
                    print_error(f"[-] Failed to create directory '{target_dir}': {e}")
                    return None, True
            else:
                print("[*] Directory not created. Please choose another destination.")
                continue

        return target_dir, False


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
        if filename.startswith("!-") or filename in (self_name, self_bat, DESTINY_FILENAME):
            print(f"[*] Skipping excluded script or system file: '{filename}'")
            continue

        eligible_files.append(filename)

    print(f"[+] Found {len(eligible_files)} eligible file(s) to move.\n")
    return eligible_files, True


def main():
    """
    Main execution function. Orchestrates loading destination choices, scanning,
    filtering, prompting for destination, and moving eligible files.
    """
    print("=" * 50)
    print("   Noterun Move to Destiny Script Initialized")
    print("=" * 50)

    script_dir = os.getcwd()
    print(f"[*] Current Directory: {script_dir}")

    destiny_file, searched_paths = find_destiny_file(script_dir)
    if destiny_file is None:
        print_error(f"[-] Destinations file '{DESTINY_FILENAME}' not found.")
        for path in searched_paths:
            print_error(f"    Searched: {path}")
        print_error(
            "    Create the file with one destination directory path per line (optional 'Label | Path')."
        )
        return 1

    print(f"[*] Destinations File: {destiny_file}\n")

    destinations, load_ok = load_destinations(destiny_file, script_dir)
    if not load_ok:
        return 1

    if not destinations:
        print_error(f"[-] No destination paths configured in '{destiny_file}'.")
        print_error(
            "    Add at least one destination directory path (one per line) and try again."
        )
        return 1

    files_to_move, scan_ok = filter_eligible_files(script_dir)
    if not scan_ok:
        return 1

    if not files_to_move:
        print("[*] No files to move. Exiting.")
        return 0

    target_dir, had_error = choose_destination(destinations, script_dir)
    if had_error:
        return 1
    if not target_dir:
        return 0

    print(f"\n[*] Target Directory: {target_dir}")
    print("-" * 50)

    success_count = 0
    failure_count = 0

    for filename in files_to_move:
        filepath = os.path.join(script_dir, filename)
        if move_file(filepath, target_dir):
            success_count += 1
        else:
            failure_count += 1

    print("-" * 50)
    print("[*] Move process completed.")
    print(f"[+] Successful moves: {success_count}")

    if failure_count > 0:
        print_error(f"[-] Failed moves: {failure_count}")
        return 1
    else:
        print("[+] All files moved successfully!")
        return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[*] Process interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print_error(f"[-] Fatal error: {e}")
        sys.exit(1)
