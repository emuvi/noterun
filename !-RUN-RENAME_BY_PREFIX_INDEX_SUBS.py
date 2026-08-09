# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import sys
import re
from typing import Optional, List, Tuple
from datetime import datetime

# Global variable for the number of zero-padded places in the index
INDEX_PADDING = 3

def get_current_time() -> str:
    """
    Returns the current time in HH:MM:SS format.
    
    Returns:
        str: Current time formatted as a string.
    """
    return datetime.now().strftime("%H:%M:%S")

def log_info(func_name: str, message: str) -> None:
    """
    Logs a general informational message.
    
    Args:
        func_name (str): The name of the function generating the log.
        message (str): The message to log.
    """
    print(f"[{get_current_time()}] ℹ️ [LOG] [{func_name}] {message}")

def log_step(func_name: str, message: str) -> None:
    """
    Logs a step start, execution, or process beginning.
    
    Args:
        func_name (str): The name of the function generating the log.
        message (str): The step message to log.
    """
    print(f"[{get_current_time()}] 🔹 [STEP] [{func_name}] {message}")

def log_success(func_name: str, message: str) -> None:
    """
    Logs a successful step completion or operation.
    
    Args:
        func_name (str): The name of the function generating the log.
        message (str): The success message to log.
    """
    print(f"[{get_current_time()}] ✅ [SUCCESS] [{func_name}] {message}")

def log_error(func_name: str, message: str) -> None:
    """
    Logs an error occurrence or failure.
    
    Args:
        func_name (str): The name of the function generating the log.
        message (str): The error details.
    """
    print(f"[{get_current_time()}] 🔴 [ERROR] [{func_name}] {message}")

def print_summary_box(total: int, successes: int, failures: int) -> None:
    """
    Prints a visual summary box with Unicode drawing characters.
    
    Args:
        total (int): Total number of files processed.
        successes (int): Number of successful operations.
        failures (int): Number of failed operations.
    """
    box_width = 47
    print(f"╔{'═' * box_width}╗")
    print(f"║{'Processing Summary'.center(box_width)}║")
    print(f"╠{'═' * box_width}╣")
    print(f"║ Total Processed: {str(total).ljust(box_width - 17)}║")
    print(f"║ Successes:       {str(successes).ljust(box_width - 17)}║")
    print(f"║ Failures:        {str(failures).ljust(box_width - 17)}║")
    print(f"╚{'═' * box_width}╝")

def is_already_prefixed(filename: str) -> bool:
    """
    Checks if the filename is already prefixed with the required format.
    
    Args:
        filename (str): The name of the file to check.
        
    Returns:
        bool: True if already prefixed, False otherwise.
    """
    pattern = rf"^\[ .*? \] - \d{{{INDEX_PADDING}}} - "
    return bool(re.match(pattern, filename))

def generate_new_filename(filename: str, index: int, user_prefix: str) -> Optional[str]:
    """
    Generates the targeted standard filename with the user prefix and index.
    
    Args:
        filename (str): The current name of the file.
        index (int): The current index to apply.
        user_prefix (str): The prefix entered by the user.
        
    Returns:
        Optional[str]: The newly generated formatted filename, or None if already correctly named.
    """
    if is_already_prefixed(filename):
        return None

    # Format the index with leading zeros based on INDEX_PADDING
    formatted_index = f"{index:0{INDEX_PADDING}d}"
    new_name = f"[ {user_prefix} ] - {formatted_index} - {filename}"
    
    return new_name

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

def rename_file(filepath: str, directory: str, filename: str, index: int, user_prefix: str) -> bool:
    """
    Handles the prefixing and renaming operation for a single file.
    
    Args:
        filepath (str): The absolute path to the source file.
        directory (str): The directory of the file.
        filename (str): The current name of the file.
        index (int): The index to use for prefixing.
        user_prefix (str): The prefix string from user input.
        
    Returns:
        bool: True if renamed or skipped intentionally, False if an error occurred.
    """
    func_name = "rename_file"
    log_step(func_name, f"Starting rename evaluation for '{filename}' with index {index} and prefix '{user_prefix}'")
    
    try:
        new_name = generate_new_filename(filename, index, user_prefix)
        if not new_name:
            log_info(func_name, f"File '{filename}' is already correctly named. Skipping rename.")
            log_success(func_name, f"Completed evaluation for '{filename}' without changes.")
            return True

        new_filepath = get_safe_target_path(directory, new_name)
        final_name = os.path.basename(new_filepath)
        
        log_info(func_name, f"Renaming from '{filepath}' to '{new_filepath}'")
        os.rename(filepath, new_filepath)
        log_success(func_name, f"Successfully renamed '{filename}' to '{final_name}'")
        return True
        
    except PermissionError as e:
        log_error(func_name, f"Permission Denied renaming '{filepath}': {e}. Ensure file is not in use.")
    except OSError as e:
        log_error(func_name, f"OS Error renaming '{filepath}': {e}. Check filesystem permissions or path limits.")
    except Exception as e:
        log_error(func_name, f"Unexpected error renaming '{filepath}': {e}.")
        
    return False

def filter_eligible_files(directory: str) -> List[Tuple[str, str]]:
    """
    Scans the directory and subfolders for files that are eligible for renaming.
    
    Args:
        directory (str): The root directory to scan.
        
    Returns:
        List[Tuple[str, str]]: A list of tuples containing (dirpath, filename).
    """
    func_name = "filter_eligible_files"
    log_step(func_name, f"Starting scan in directory '{directory}' and subfolders")
    
    eligible_files = []
    
    for dirpath, dirnames, filenames in os.walk(directory):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            
            # Ignore system/script files, files starting with _, or .py/.url/.lnk files
            if filename.startswith('!-') or filename.startswith('_') or filename == os.path.basename(__file__) or filename.lower().endswith(('.py', '.url', '.lnk')):
                continue
                
            eligible_files.append((dirpath, filename))
        
    log_success(func_name, f"Completed scan. Found {len(eligible_files)} eligible file(s).")
    return eligible_files

def get_max_existing_index(files_to_process: List[Tuple[str, str]]) -> int:
    """
    Scans the eligible files to find the highest existing index to prevent duplications.
    
    Args:
        files_to_process (List[Tuple[str, str]]): List of files to process.
        
    Returns:
        int: The highest existing index found.
    """
    func_name = "get_max_existing_index"
    log_step(func_name, "Starting to scan for max existing index")
    
    max_existing_index = 0
    pattern = rf"^\[ .*? \] - (\d{{{INDEX_PADDING}}}) - "
    
    for dirpath, filename in files_to_process:
        match = re.match(pattern, filename)
        if match:
            try:
                idx = int(match.group(1))
                if idx > max_existing_index:
                    max_existing_index = idx
            except ValueError:
                log_error(func_name, f"Failed to parse index from '{filename}'")
                pass
                
    log_success(func_name, f"Completed. Max existing index found: {max_existing_index}")
    return max_existing_index

def process_renaming_cycle(files_to_process: List[Tuple[str, str]], start_index: int, user_prefix: str) -> Tuple[int, int]:
    """
    Orchestrates the iteration over files and manages the loop logging and renaming calls.
    
    Args:
        files_to_process (List[Tuple[str, str]]): Files eligible for renaming.
        start_index (int): The index to start assigning to new files.
        user_prefix (str): The prefix string to add to the files.
        
    Returns:
        Tuple[int, int]: A tuple containing (success_count, failure_count).
    """
    func_name = "process_renaming_cycle"
    total_files = len(files_to_process)
    log_step(func_name, f"Starting renaming cycle for {total_files} files with start index {start_index}")
    
    success_count = 0
    failure_count = 0
    current_index = start_index
    
    for i, (dirpath, filename) in enumerate(files_to_process, 1):
        log_step(func_name, f"Processing item {i} of {total_files}")
        filepath = os.path.join(dirpath, filename)
        log_info(func_name, f"Processing: '{filename}' at '{dirpath}'")
        
        if is_already_prefixed(filename):
            log_info(func_name, f"Skipping file '{filename}' - already correctly prefixed")
            success_count += 1
            log_success(func_name, f"Item {i} handled successfully (skipped)")
            continue
            
        if rename_file(filepath, dirpath, filename, current_index, user_prefix):
            success_count += 1
            current_index += 1
            log_success(func_name, f"Item {i} renamed successfully")
        else:
            failure_count += 1
            log_error(func_name, f"Failed to rename item {i}")
            
    log_success(func_name, f"Completed renaming cycle. Successes: {success_count}, Failures: {failure_count}")
    return success_count, failure_count

def main():
    """
    Main execution function. Orchestrates the filtering, prefix-index calculation,
    and renaming process for files within the script's directory and subfolders.
    """
    func_name = "main"
    print("=" * 50)
    print("   Noterun Prefix-Index Rename Script (Recursive) Initialized")
    print("=" * 50)
    log_step(func_name, "Starting main process")
    
    user_prefix = input("Enter the string to use as prefix: ").strip()
    if not user_prefix:
        log_error(func_name, "No prefix entered. Exiting.")
        return 0

    script_dir = os.path.dirname(os.path.abspath(__file__))
    files_to_process = filter_eligible_files(script_dir)
    
    if not files_to_process:
        log_info(func_name, "No files to process. Exiting.")
        print_summary_box(0, 0, 0)
        return 0
        
    # Sort files to ensure consistent indexing (by modification time, oldest first)
    log_step(func_name, "Sorting files by modification time")
    files_to_process.sort(key=lambda x: os.path.getmtime(os.path.join(x[0], x[1])))
    log_success(func_name, "Files sorted successfully")
    
    max_existing_index = get_max_existing_index(files_to_process)
    current_index = max_existing_index + 1
    
    success_count, failure_count = process_renaming_cycle(files_to_process, current_index, user_prefix)
    
    log_step(func_name, "Generating summary report")
    print_summary_box(len(files_to_process), success_count, failure_count)
    log_success(func_name, "Main process completed")
    
    if failure_count > 0:
        return 1
    else:
        return 0

if __name__ == '__main__':
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code)
