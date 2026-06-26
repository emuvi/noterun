# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import sys
import re
from typing import Optional

def prettify_name_logic(name: str) -> str:
    """
    Applies the prettification logic to a filename string.
    - Adds spaces before CamelCase/PascalCase boundaries.
    - Replaces underscores and hyphens with spaces.
    - Preserves uppercase acronyms (siglas).
    - Capitalizes words longer than 3 characters, and the first word.
    - Lowercases words 3 characters or shorter (if not the first word, not already TitleCased, and not a sigla).
    """
    # 1. CamelCase splitting: add space between lowercase/number and uppercase
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', name)
    # Add space between uppercase and uppercase followed by lowercase (e.g., XMLParser -> XML Parser)
    name = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', name)
    
    # 2. Replace _ and - with spaces
    name = name.replace('_', ' ').replace('-', ' ')
    
    # 3. Split into words
    words = name.split()
    
    new_words = []
    for i, word in enumerate(words):
        # Check if sigla (acronym): all letters are uppercase and at least one letter exists
        is_sigla = word.isupper() and any(c.isalpha() for c in word)
        
        if is_sigla:
            new_words.append(word)
        elif len(word) > 3:
            # Word is larger than 3 characters, capitalize it (Title Case)
            new_words.append(word.capitalize())
        else:
            # Word is 3 or fewer characters
            if i == 0:
                new_words.append(word.capitalize())
            else:
                # If it was already title cased (like 'My' from CamelCase), keep it
                if word.istitle():
                    new_words.append(word)
                else:
                    new_words.append(word.lower())
                
    # 4. Rejoin with a single space
    return " ".join(new_words)

def generate_new_filename(filename: str) -> Optional[str]:
    """
    Generates the targeted prettified filename.
    
    Args:
        filename (str): The current name of the file.
        
    Returns:
        str: The newly generated formatted filename, or None if already correctly named.
    """
    name_part, ext = os.path.splitext(filename)
    
    prettified_name = prettify_name_logic(name_part)
    
    if not prettified_name:
        return None
        
    new_name = f"{prettified_name}{ext}"
    
    if new_name == filename:
        return None
        
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

def rename_file(filepath: str, directory: str, filename: str) -> bool:
    """
    Handles the prettification and renaming operation for a single file.
    
    Args:
        filepath (str): The absolute path to the source file.
        directory (str): The directory of the file.
        filename (str): The current name of the file.
        
    Returns:
        bool: True if renamed or skipped intentionally, False if an error occurred.
    """
    try:
        new_name = generate_new_filename(filename)
        if not new_name:
            # File is already correctly named
            print(f"[*] Skipping file...")
            print(f"    File: '{filepath}'")
            print(f"    Reason: Already perfectly formatted.\n")
            return True

        new_filepath = get_safe_target_path(directory, new_name)
        final_name = os.path.basename(new_filepath)
        
        print(f"[*] Renaming file...")
        print(f"    From: '{filepath}'")
        print(f"    To:   '{new_filepath}'")
        
        os.rename(filepath, new_filepath)
        print(f"[+] Successfully renamed '{filename}' to '{final_name}'.\n")
        return True
        
    except PermissionError as e:
        print(f"[-] Permission Denied renaming '{filepath}': {e}\n")
    except OSError as e:
        print(f"[-] OS Error renaming '{filepath}': {e}\n")
    except Exception as e:
        print(f"[-] Unexpected error renaming '{filepath}': {e}\n")
        
    return False

def filter_eligible_files(directory: str) -> list:
    """
    Scans the directory and subfolders for files that are eligible for renaming.
    
    Args:
        directory (str): The root directory to scan.
        
    Returns:
        list: A list of tuples (dirpath, filename).
    """
    print(f"[*] Scanning directory '{directory}' and subfolders for files to rename...")
    eligible_files = []
    
    for dirpath, dirnames, filenames in os.walk(directory):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            
            # Ignore system/script files or .py/.url/.lnk files
            if filename.startswith('!-') or filename == os.path.basename(__file__) or filename.lower().endswith(('.py', '.url', '.lnk')):
                continue
                
            eligible_files.append((dirpath, filename))
        
    print(f"[+] Found {len(eligible_files)} eligible file(s) for renaming evaluation.\n")
    return eligible_files

def main():
    """
    Main execution function. Orchestrates the filtering and prettify renaming
    of files within the script's directory and its subfolders.
    """
    print("=" * 70)
    print("   Noterun Prettify Name Script (Recursive) Initialized")
    print("=" * 70)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    files_to_process = filter_eligible_files(script_dir)
    
    if not files_to_process:
        print("[*] No files to process. Exiting.")
        return 0
        
    print("-" * 70)
    
    success_count = 0
    failure_count = 0
    
    for dirpath, filename in files_to_process:
        filepath = os.path.join(dirpath, filename)
            
        if rename_file(filepath, dirpath, filename):
            success_count += 1
        else:
            failure_count += 1
            
    print("-" * 70)
    print(f"[*] Renaming process completed.")
    print(f"[+] Processed successfully: {success_count}")
    
    if failure_count > 0:
        print(f"[-] Errors encountered: {failure_count}")
        return 1
    else:
        print("[+] All files processed without errors!")
        return 0

if __name__ == '__main__':
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code)
