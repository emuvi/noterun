import os
import subprocess
import sys
from typing import Optional

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
            check=True
        )
        duration = float(result.stdout.strip())
        print(f"[+] Duration found: {duration:.2f} seconds.")
        return duration
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        print(f"[-] ffprobe process failed for '{filename}'. Error:\n    {error_msg}")
    except FileNotFoundError:
        print(f"[-] 'ffprobe' not found. Ensure ffmpeg is installed and added to your system PATH.")
    except Exception as e:
        print(f"[-] Unexpected error getting duration for '{filename}': {e}")
        
    return None

def verify_and_cleanup(filepath: str, part1_path: str, part2_path: str, filename: str) -> bool:
    """
    Verifies that the split was successful and cleans up the original file.
    
    Args:
        filepath (str): Original file path.
        part1_path (str): First split part path.
        part2_path (str): Second split part path.
        filename (str): Original filename.
        
    Returns:
        bool: True if validation passed and cleanup was successful, False otherwise.
    """
    if not (os.path.exists(part1_path) and os.path.exists(part2_path)):
        print(f"[-] Splitting failed: Expected part files were not found after ffmpeg execution.\n")
        return False
        
    if os.path.getsize(part1_path) <= 0 or os.path.getsize(part2_path) <= 0:
        print(f"[-] Splitting failed: Generated parts are empty.\n")
        return False
        
    print(f"[+] Splitting verified. Deleting original file '{filename}'...")
    try:
        os.remove(filepath)
        print(f"[+] Original file deleted successfully.\n")
        return True
    except OSError as e:
        print(f"[-] OS Error: Could not delete original file '{filename}': {e}\n")
    except Exception as e:
        print(f"[-] Unexpected error while deleting original file '{filename}': {e}\n")
        
    return False

def execute_ffmpeg_split(filepath: str, target_path: str, duration_args: list, part_name: str) -> bool:
    """
    Executes an ffmpeg command to extract a portion of a video.
    
    Args:
        filepath (str): The source file.
        target_path (str): The output file.
        duration_args (list): The list of arguments to specify duration (e.g., ['-t', '...'] or ['-ss', '...']).
        part_name (str): Label for logging (e.g., 'Part 1').
        
    Returns:
        bool: True if ffmpeg executes successfully, False otherwise.
    """
    print(f"[*] Executing ffmpeg for {part_name}...")
    try:
        cmd = ['ffmpeg', '-y', '-i', filepath] + duration_args + ['-c', 'copy', target_path]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"[+] {part_name} created successfully.")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        print(f"[-] ffmpeg failed while creating {part_name}. Error:\n    {error_msg}\n")
    except FileNotFoundError:
        print(f"[-] 'ffmpeg' not found. Ensure ffmpeg is installed and added to your system PATH.\n")
    except Exception as e:
        print(f"[-] Unexpected error executing ffmpeg for {part_name}: {e}\n")
        
    return False

def split_media_file(filepath: str, directory: str, filename: str, duration: float) -> bool:
    """
    Splits the media file into two equal halves using ffmpeg.
    
    Args:
        filepath (str): The absolute path to the file.
        directory (str): The directory containing the file.
        filename (str): The file's name.
        duration (float): The total duration of the media file in seconds.
        
    Returns:
        bool: True if the file was split successfully, False otherwise.
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
                print(f"[-] Failed to delete existing part '{p_name}': {e}\n")
                return False

    print(f"[*] Splitting '{filename}' into two halves.")
    print(f"    Part 1: '{part1_name}' (0s to {half_time:.2f}s)")
    print(f"    Part 2: '{part2_name}' ({half_time:.2f}s to end)")
    
    # Extract First Half
    if not execute_ffmpeg_split(filepath, part1_path, ['-t', str(half_time)], "Part 1"):
        return False
        
    # Extract Second Half
    if not execute_ffmpeg_split(filepath, part2_path, ['-ss', str(half_time)], "Part 2"):
        return False

    # Verify and cleanup
    return verify_and_cleanup(filepath, part1_path, part2_path, filename)

def process_file(filepath: str, directory: str, filename: str) -> bool:
    """
    Checks the file size and triggers splitting if the size exceeds MAX_SIZE.
    
    Args:
        filepath (str): Path to the file.
        directory (str): Directory containing the file.
        filename (str): Name of the file.
        
    Returns:
        bool: True if processed successfully or skipped naturally, False on error.
    """
    try:
        size = os.path.getsize(filepath)
    except OSError as e:
        print(f"[-] OS Error: Could not retrieve size for '{filename}': {e}")
        return False

    if size > MAX_SIZE:
        size_mb = size / (1024 * 1024)
        print(f"[*] File '{filename}' is {size_mb:.2f}MB (Exceeds 180MB limit). Initiating split.")
        
        duration = get_duration(filepath)
        if duration:
            return split_media_file(filepath, directory, filename, duration)
        else:
            print(f"[-] Skipping '{filename}' due to duration retrieval failure.\n")
            return False
            
    return True

def filter_media_files(directory: str) -> list:
    """
    Filters the directory to find media files eligible for size checking.
    
    Args:
        directory (str): Directory to scan.
        
    Returns:
        list: A list of media filenames.
    """
    print(f"[*] Scanning directory '{directory}' for media files to check...")
    media_files = []
    
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
            
        if filename.startswith('!-') or filename == os.path.basename(__file__):
            continue
            
        if not filename.lower().endswith(('.mp4', '.mp3')):
            continue

        media_files.append(filename)
        
    print(f"[+] Found {len(media_files)} media file(s) for size evaluation.\n")
    return media_files

def main():
    """
    Main execution function. Orchestrates the scanning and potential splitting
    of large media files.
    """
    print("=" * 50)
    print("   Noterun Large Media Split Script Initialized")
    print("=" * 50)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    media_files = filter_media_files(script_dir)
    
    if not media_files:
        print("[*] No target media files found. Exiting.")
        input("\nPress Enter to exit...")
        sys.exit(0)
        
    print("-" * 50)
    
    success_count = 0
    failure_count = 0
    
    for filename in media_files:
        filepath = os.path.join(script_dir, filename)
        if process_file(filepath, script_dir, filename):
            success_count += 1
        else:
            failure_count += 1
            
    print("-" * 50)
    print(f"[*] Media evaluation process completed.")
    print(f"[+] Successfully evaluated/processed: {success_count}")
    
    if failure_count > 0:
        print(f"[-] Errors encountered during processing: {failure_count}")
    else:
        print("[+] All files processed without errors!")
        
    input("\nPress Enter to exit...")

if __name__ == '__main__':
    main()
    input()
