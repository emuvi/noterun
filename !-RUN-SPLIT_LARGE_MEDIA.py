# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import subprocess
import sys
import time
from typing import Optional

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

# ==============================================================================
# GLOBAL CONFIGURATION
# ==============================================================================
# Determines whether to delete origin files after processing.
# True  -> Deletes the files automatically without asking.
# False -> Keeps the files without asking.
# None  -> Prompts the user to decide.
DELETE_ORIGIN_FILES = None
# ==============================================================================

MAX_SIZE = 180 * 1024 * 1024  # 180 MB

def get_duration(filepath: str) -> Optional[float]:
    """
    Gets the duration of the media file using ffprobe.
    
    Args:
        filepath (str): The absolute path to the media file.
        
    Returns:
        float: The duration of the media file in seconds, or None if extraction fails.
    """
    filename = os.path.basename(filepath)
    print(f"[*] Fetching duration for '{filename}' via ffprobe...")
    
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
             '-of', 'default=noprint_wrappers=1:nokey=1', filepath],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=True
        )
        duration = float(result.stdout.strip())
        if duration <= 0:
            print_error(f"[-] Invalid media duration ({duration}) for '{filename}'.")
            return None
        print(f"[+] Duration found: {duration:.2f} seconds.")
        return duration
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        print_error(f"[-] ffprobe process failed for '{filename}'. Error:\n    {error_msg}")
    except FileNotFoundError:
        print_error(f"[-] 'ffprobe' not found. Ensure ffmpeg is installed and added to your system PATH.")
    except Exception as e:
        print_error(f"[-] Unexpected error getting duration for '{filename}': {e}")
        
    return None

def verify_and_cleanup(filepath: str, part1_path: str, part2_path: str, filename: str) -> bool:
    """
    Verifies that the split was successful and cleans up the original file.
    """
    if not (os.path.exists(part1_path) and os.path.exists(part2_path)):
        print_error(f"[-] Splitting failed: Expected part files were not found after ffmpeg execution.\n")
        return False
        
    if os.path.getsize(part1_path) <= 0 or os.path.getsize(part2_path) <= 0:
        print_error(f"[-] Splitting failed: Generated parts are empty.\n")
        return False
        
    print(f"[+] Splitting verified. Original file '{filename}' kept for now.\n")
    return True

def execute_ffmpeg_split(filepath: str, target_path: str, duration_args: list, part_name: str) -> bool:
    """
    Executes an ffmpeg command to extract a portion of a video/audio file.
    Falls back to re-encoding if stream copy fails.
    """
    print(f"[*] Executing ffmpeg for {part_name}...")
    cmd = ['ffmpeg', '-y', '-i', filepath] + duration_args + ['-c', 'copy', target_path]
    fallback_cmd = ['ffmpeg', '-y', '-err_detect', 'ignore_err', '-i', filepath] + duration_args + [target_path]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
        print(f"[+] {part_name} created successfully.")
        return True
    except FileNotFoundError:
        print_error(f"[-] 'ffmpeg' not found. Ensure ffmpeg is installed and added to your system PATH.\n")
        return False
    except subprocess.CalledProcessError as e:
        print(f"[*] Stream copy failed for {part_name}. Retrying with re-encode fallback...")
        try:
            subprocess.run(fallback_cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            print(f"[+] {part_name} created successfully (re-encode fallback).")
            return True
        except subprocess.CalledProcessError as e2:
            error_msg = e2.stderr.strip() if e2.stderr else (e.stderr.strip() if e.stderr else str(e2))
            print_error(f"[-] ffmpeg failed while creating {part_name}. Error:\n    {error_msg}\n")
        except Exception as e2:
            print_error(f"[-] Fallback ffmpeg error for {part_name}: {e2}\n")
    except Exception as e:
        print_error(f"[-] Unexpected error executing ffmpeg for {part_name}: {e}\n")
        
    return False

def split_media_file(filepath: str, directory: str, filename: str, duration: float) -> bool:
    """
    Splits the media file into two equal halves using ffmpeg.
    """
    half_time = duration / 2.0
    name_part, ext = os.path.splitext(filename)
    
    part1_name = f"{name_part}_part1{ext}"
    part2_name = f"{name_part}_part2{ext}"
    part1_path = os.path.join(directory, part1_name)
    part2_path = os.path.join(directory, part2_name)
    
    # Pre-split cleanup: remove existing parts to prevent ffmpeg overwrite conflicts
    for p_path, p_name in [(part1_path, part1_name), (part2_path, part2_name)]:
        if os.path.exists(p_path):
            print(f"[*] Existing part found: '{p_name}'. Deleting before proceeding...")
            try:
                os.remove(p_path)
            except OSError as e:
                print_error(f"[-] Failed to delete existing part '{p_name}': {e}\n")
                return False

    print(f"[*] Splitting '{filename}' into two halves.")
    print(f"    Part 1: '{part1_name}' (0s to {half_time:.2f}s)")
    print(f"    Part 2: '{part2_name}' ({half_time:.2f}s to end)")
    
    # Extract First Half
    if not execute_ffmpeg_split(filepath, part1_path, ['-t', str(half_time)], "Part 1"):
        for p in (part1_path, part2_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        return False
        
    # Extract Second Half
    if not execute_ffmpeg_split(filepath, part2_path, ['-ss', str(half_time)], "Part 2"):
        for p in (part1_path, part2_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        return False

    # Verify and cleanup
    if not verify_and_cleanup(filepath, part1_path, part2_path, filename):
        for p in (part1_path, part2_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        return False
    return True

def process_file(filepath: str, directory: str, filename: str) -> tuple:
    """
    Checks the file size and triggers splitting if the size exceeds MAX_SIZE.
    """
    try:
        size = os.path.getsize(filepath)
    except OSError as e:
        print_error(f"[-] OS Error: Could not retrieve size for '{filename}': {e}")
        return False, False

    if size > MAX_SIZE:
        size_mb = size / (1024 * 1024)
        print(f"[*] File '{filename}' is {size_mb:.2f}MB (Exceeds 180MB limit). Initiating split.")
        
        duration = get_duration(filepath)
        if duration:
            return split_media_file(filepath, directory, filename, duration), True
        else:
            print_error(f"[-] Skipping '{filename}' due to duration retrieval failure.\n")
            return False, False
            
    return True, False

def filter_media_files(directory: str) -> tuple:
    """
    Filters the directory to find media files eligible for size checking.
    """
    print(f"[*] Scanning directory '{directory}' for media files to check...")
    media_files = []
    
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
            
        if filename.startswith('!-') or filename in (self_name, self_bat):
            continue
            
        if not filename.lower().endswith(('.mp4', '.mp3')):
            continue

        media_files.append(filename)
        
    print(f"[+] Found {len(media_files)} media file(s) for size evaluation.\n")
    return media_files, True

def main():
    """
    Main execution function. Orchestrates the scanning and potential splitting
    of large media files.
    """
    print("=" * 50)
    print("   Noterun Large Media Split Script Initialized")
    print("=" * 50)
    
    script_dir = os.getcwd()
    media_files, scan_ok = filter_media_files(script_dir)
    if not scan_ok:
        return 1
    
    if not media_files:
        print("[*] No target media files found. Exiting.")
        return 0
        
    print("-" * 50)
    
    success_count = 0
    failure_count = 0
    processed_files = []
    
    for filename in media_files:
        filepath = os.path.join(script_dir, filename)
        success, splitted = process_file(filepath, script_dir, filename)
        if success:
            success_count += 1
            if splitted:
                processed_files.append(filepath)
        else:
            failure_count += 1
            
    print("-" * 50)
    print(f"[*] Media evaluation process completed.")
    print(f"[+] Successfully evaluated/processed: {success_count}")
    
    if failure_count > 0:
        print_error(f"[-] Errors encountered during processing: {failure_count}")
    else:
        print("[+] All files processed without errors!")

    if processed_files:
        if DELETE_ORIGIN_FILES is True:
            ans = 'y'
        elif DELETE_ORIGIN_FILES is False:
            ans = 'n'
        else:
            try:
                ans = read_input("\nDo you want to delete the origin files? (Y/N): ")
            except (EOFError, KeyboardInterrupt):
                ans = 'n'
            
        if ans.strip().lower() == 'y':
            for fp in processed_files:
                deleted = False
                last_err = None
                for attempt in range(1, 4):
                    try:
                        os.remove(fp)
                        print(f"[+] Arquivo de origem excluído: {os.path.basename(fp)}")
                        deleted = True
                        break
                    except Exception as e:
                        last_err = e
                        if attempt < 3:
                            time.sleep(0.4 * attempt)
                if not deleted:
                    failure_count += 1
                    print_error(f"[-] Erro ao excluir {os.path.basename(fp)}: {last_err}")

    return 1 if failure_count > 0 else 0

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
