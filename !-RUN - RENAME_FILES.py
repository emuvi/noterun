import os
import datetime

def get_file_time(filepath):
    """
    Retrieves the file's creation time, falling back to modification time if necessary.
    Returns a datetime object or None if an error occurs.
    """
    try:
        stat = os.stat(filepath)
        # On Windows, st_ctime is usually creation time.
        return datetime.datetime.fromtimestamp(stat.st_ctime)
    except AttributeError:
        return datetime.datetime.fromtimestamp(stat.st_mtime)
    except Exception as e:
        print(f"[ERROR] Could not get file time for '{os.path.basename(filepath)}': {e}")
        return None

def parse_date_prefix(filename):
    """
    Attempts to parse date/time prefix from the filename based on known formats.
    Returns the parsed datetime, the remaining filename, and the matched format string.
    """
    formats = [
        "%Y.%m.%d_%H.%M.%S", "%Y-%m-%d_%H-%M-%S", "%Y.%m.%d %H.%M.%S",
        "%Y-%m-%d %H:%M:%S", "%Y.%m.%d-%H.%M.%S", "%Y.%m.%d",
        "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y",
        "%Y%m%d_%H%M%S", "%Y%m%d"
    ]
    
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

def generate_new_filename(filename, filepath):
    """
    Generates the targeted standard filename using parsed or file system dates.
    Returns the new filename or None if no change is needed.
    """
    dt, rest_of_name, fmt = parse_date_prefix(filename)
    target_fmt = "%Y.%m.%d_%H.%M.%S"

    if dt:
        # If perfectly formatted already, skip
        if fmt == target_fmt and filename.startswith(dt.strftime(target_fmt) + " - "):
            return None
            
        # If format misses hour, inject file time hour/min/sec
        if fmt and '%H' not in fmt:
            file_dt = get_file_time(filepath)
            if file_dt:
                dt = dt.replace(hour=file_dt.hour, minute=file_dt.minute, second=file_dt.second)
    else:
        # No date recognized, use file's metadata time
        dt = get_file_time(filepath)
        if not dt:
            return None # Cannot process without a valid date
        rest_of_name = filename
        
        # Clean leading separators
        if rest_of_name.startswith(' - '):
            rest_of_name = rest_of_name[3:]
        elif rest_of_name.startswith('- ') or rest_of_name.startswith(' -'):
            rest_of_name = rest_of_name[2:]

    formatted_dt = dt.strftime(target_fmt)
    new_name = f"{formatted_dt} - {rest_of_name}"
    
    return new_name if new_name != filename else None

def get_safe_target_path(directory, filename):
    """
    Generates a unique file path avoiding overwriting existing files.
    """
    target_path = os.path.join(directory, filename)
    name_part, ext = os.path.splitext(filename)
    counter = 1
    
    while os.path.exists(target_path):
        new_name = f"{name_part} ({counter}){ext}"
        target_path = os.path.join(directory, new_name)
        counter += 1
        
    return target_path

def rename_file(filepath, directory, filename):
    """
    Handles the renaming operation and exceptions for a single file.
    """
    try:
        new_name = generate_new_filename(filename, filepath)
        if not new_name:
            # Uncomment below if you want verbose skipping output
            # print(f"[SKIP] '{filename}' is already formatted or cannot be processed.")
            return

        new_filepath = get_safe_target_path(directory, new_name)
        final_name = os.path.basename(new_filepath)
        
        print(f"[INFO] Renaming:\n  Source: '{filename}'\n  Target: '{final_name}'")
        os.rename(filepath, new_filepath)
        print(f"[SUCCESS] Renamed '{filename}' successfully.\n")
        
    except PermissionError as e:
        print(f"[ERROR] Permission denied renaming '{filename}': {e}\n")
    except Exception as e:
        print(f"[ERROR] Unexpected error renaming '{filename}': {e}\n")

def process_directory(directory):
    """
    Iterates through the directory to parse dates and rename files consistently.
    """
    print(f"[START] Processing directory for renaming: '{directory}'\n")
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
            
        if filename.startswith('!-') or filename == os.path.basename(__file__) or filename.lower().endswith(('.py', '.url')):
            # Uncomment below if you want verbose skipping output
            # print(f"[SKIP] Ignoring system/script file: '{filename}'")
            continue

        rename_file(filepath, directory, filename)
        
    print(f"[FINISHED] Directory renaming completed for '{directory}'.")

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    process_directory(script_dir)
    input()
