import os
import shutil
import sys

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
    target_path = get_safe_target_path(target_dir, filename)
    
    print(f"[*] Moving '{filename}'...")
    print(f"    Source: {source_path}")
    print(f"    Target: {target_path}")
    
    try:
        shutil.move(source_path, target_path)
        print(f"[+] Successfully moved '{filename}'.\n")
        return True
    except PermissionError as e:
        print(f"[-] Permission Denied while moving '{filename}': {e}\n")
    except FileNotFoundError as e:
        print(f"[-] File Not Found Error for '{filename}': {e}\n")
    except OSError as e:
        print(f"[-] OS Error while moving '{filename}': {e}\n")
    except Exception as e:
        print(f"[-] An unexpected error occurred while moving '{filename}': {e}\n")
        
    return False

def filter_eligible_files(directory: str) -> list:
    """
    Filters files in the given directory to find those eligible for moving.
    Ignores directories, the script itself, and files starting with '!-'.
    
    Args:
        directory (str): The directory to scan.
        
    Returns:
        list: A list of filenames eligible to be moved.
    """
    print(f"[*] Scanning directory '{directory}' for files to move...")
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

        # Only process files
        if not os.path.isfile(filepath):
            continue

        # Skip system/script files or files explicitly marked with '!-RUN' or similar
        if filename.startswith('!-') or filename == os.path.basename(__file__):
            print(f"[*] Skipping excluded script or system file: '{filename}'")
            continue

        eligible_files.append(filename)
        
    print(f"[+] Found {len(eligible_files)} eligible file(s) to move.\n")
    return eligible_files

def main():
    """
    Main execution function. Orchestrates the scanning, filtering, and moving
    of eligible files to the parent directory.
    """
    print("=" * 50)
    print("   Noterun Move to Parent Script Initialized")
    print("=" * 50)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    
    print(f"[*] Current Directory: {script_dir}")
    print(f"[*] Target Parent Directory: {parent_dir}\n")

    files_to_move = filter_eligible_files(script_dir)
    
    if not files_to_move:
        print("[*] No files to move. Exiting.")
        input("\nPress Enter to exit...")
        sys.exit(0)
        
    print("-" * 50)
    
    success_count = 0
    failure_count = 0
    
    for filename in files_to_move:
        filepath = os.path.join(script_dir, filename)
        if move_file(filepath, parent_dir):
            success_count += 1
        else:
            failure_count += 1

    print("-" * 50)
    print(f"[*] Move process completed.")
    print(f"[+] Successful moves: {success_count}")
    
    if failure_count > 0:
        print(f"[-] Failed moves: {failure_count}")
    else:
        print("[+] All files moved successfully!")
        
    input("\nPress Enter to exit...")

if __name__ == '__main__':
    main()
    input()
