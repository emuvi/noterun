import os
import subprocess

MAX_SIZE = 180 * 1024 * 1024  # 180 MB

def get_duration(filepath):
    """
    Gets the duration of the media file using ffprobe.
    Returns duration as float or None on failure.
    """
    print(f"[INFO] Fetching duration for '{os.path.basename(filepath)}' via ffprobe...")
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
             '-of', 'default=noprint_wrappers=1:nokey=1', filepath],
            capture_output=True,
            text=True,
            check=True
        )
        duration = float(result.stdout.strip())
        print(f"[SUCCESS] Duration found: {duration:.2f} seconds.")
        return duration
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] ffprobe process failed for '{os.path.basename(filepath)}'. Error:\n{e.stderr.strip() if e.stderr else str(e)}")
        return None
    except FileNotFoundError:
        print(f"[ERROR] 'ffprobe' not found. Please ensure ffmpeg is installed and added to PATH.")
        return None
    except Exception as e:
        print(f"[ERROR] Unexpected error getting duration for '{os.path.basename(filepath)}': {e}")
        return None

def split_media_file(filepath, directory, filename, duration):
    """
    Splits the media file into two equal halves using ffmpeg.
    Deletes existing parts if they already exist.
    If splitting is successful, deletes the original file.
    """
    half_time = duration / 2.0
    name_part, ext = os.path.splitext(filename)
    
    part1_name = f"{name_part}_part1{ext}"
    part2_name = f"{name_part}_part2{ext}"
    
    part1_path = os.path.join(directory, part1_name)
    part2_path = os.path.join(directory, part2_name)
    
    # 1) Check if parts already exist and delete them
    for p_path, p_name in [(part1_path, part1_name), (part2_path, part2_name)]:
        if os.path.exists(p_path):
            print(f"[INFO] Existing part found: '{p_name}'. Deleting before proceeding...")
            try:
                os.remove(p_path)
            except Exception as e:
                print(f"[ERROR] Failed to delete existing part '{p_name}': {e}\n")
                return False

    print(f"[INFO] Splitting '{filename}' into two halves.")
    print(f"       Part 1: '{part1_name}' (0s to {half_time:.2f}s)")
    print(f"       Part 2: '{part2_name}' ({half_time:.2f}s to end)")
    
    # Extract first half
    try:
        print(f"[INFO] Executing ffmpeg for Part 1...")
        subprocess.run(['ffmpeg', '-y', '-i', filepath, '-t', str(half_time), '-c', 'copy', part1_path], 
                       check=True, capture_output=True, text=True)
        print(f"[SUCCESS] Part 1 created successfully.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] ffmpeg failed while creating Part 1 of '{filename}'. Error:\n{e.stderr.strip() if e.stderr else str(e)}\n")
        return False
    except FileNotFoundError:
        print(f"[ERROR] 'ffmpeg' not found. Please ensure ffmpeg is installed and added to PATH.\n")
        return False
        
    # Extract second half
    try:
        print(f"[INFO] Executing ffmpeg for Part 2...")
        subprocess.run(['ffmpeg', '-y', '-i', filepath, '-ss', str(half_time), '-c', 'copy', part2_path], 
                       check=True, capture_output=True, text=True)
        print(f"[SUCCESS] Part 2 created successfully.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] ffmpeg failed while creating Part 2 of '{filename}'. Error:\n{e.stderr.strip() if e.stderr else str(e)}\n")
        return False

    # 2) After split, check if successful and delete original
    if os.path.exists(part1_path) and os.path.exists(part2_path):
        # Also verify they aren't empty, just to be safe
        if os.path.getsize(part1_path) > 0 and os.path.getsize(part2_path) > 0:
            print(f"[SUCCESS] Splitting verified. Deleting original file '{filename}'...")
            try:
                os.remove(filepath)
                print(f"[SUCCESS] Original file deleted.\n")
                return True
            except Exception as e:
                print(f"[ERROR] Could not delete original file '{filename}': {e}\n")
                return False
        else:
            print(f"[ERROR] Splitting failed: Generated parts are empty.\n")
            return False
    else:
        print(f"[ERROR] Splitting failed: Part files were not found after ffmpeg execution.\n")
        return False

def process_file(filepath, directory, filename):
    """
    Checks the file size and triggers splitting if necessary.
    """
    try:
        size = os.path.getsize(filepath)
    except Exception as e:
        print(f"[ERROR] Could not get size of '{filename}': {e}")
        return

    if size > MAX_SIZE:
        print(f"[INFO] File '{filename}' is {(size / (1024*1024)):.2f}MB (larger than 180MB limit). Initiating split.")
        duration = get_duration(filepath)
        if duration:
            split_media_file(filepath, directory, filename, duration)
        else:
            print(f"[WARNING] Skipping '{filename}' due to duration retrieval failure.\n")
    else:
        pass
        # Uncomment below if you want verbose skipping output
        # print(f"[SKIP] File '{filename}' is {(size / (1024*1024)):.2f}MB, no split required.")

def process_directory(directory):
    """
    Iterates through the directory to find and split large media files.
    """
    print(f"[START] Processing directory for large media: '{directory}'\n")
    try:
        files = os.listdir(directory)
    except PermissionError as e:
        print(f"[FATAL] Permission denied accessing directory '{directory}': {e}")
        return
    except Exception as e:
        print(f"[FATAL] Unexpected error accessing directory '{directory}': {e}")
        return

    for filename in files:
        filepath = os.path.join(directory, filename)
        
        if not os.path.isfile(filepath):
            continue
            
        if filename.startswith('!-') or filename == os.path.basename(__file__) or not filename.lower().endswith(('.mp4', '.mp3')):
            continue
            
        # Removed safety check for "_part1." / "_part2." to allow recursive splitting
        # if the parts themselves still exceed 180MB.

        process_file(filepath, directory, filename)

    print(f"[FINISHED] Directory media splitting completed for '{directory}'.")

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    process_directory(script_dir)
    input()
