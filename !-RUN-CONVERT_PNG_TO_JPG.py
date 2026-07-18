# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import sys
from PIL import Image

def convert_image(filepath: str, directory: str, filename: str) -> bool:
    """
    Handles the operation to convert a single PNG file to JPG.
    """
    jpg_filename = os.path.splitext(filename)[0] + ".jpg"
    jpg_path = os.path.join(directory, jpg_filename)

    if os.path.exists(jpg_path):
        print(f"[*] Skipping file...")
        print(f"    File: '{filename}'")
        print(f"    Reason: Target '{jpg_filename}' already exists\n")
        return True

    try:
        print(f"[*] Converting file...")
        print(f"    From: '{filename}'")
        print(f"    To:   '{jpg_filename}'")
        
        # Open the image
        img = Image.open(filepath)
        
        # Convert to RGB, as JPEG doesn't support alpha channel (transparency)
        rgb_im = img.convert('RGB')
        
        # Save as JPG
        rgb_im.save(jpg_path, quality=95)
        print(f"[+] Successfully converted '{filename}'.\n")
        return True
        
    except PermissionError as e:
        print(f"[-] Permission Denied converting '{filename}': {e}\n")
    except OSError as e:
        print(f"[-] OS Error converting '{filename}': {e}\n")
    except Exception as e:
        print(f"[-] Unexpected error converting '{filename}': {e}\n")
        
    return False

def filter_eligible_files(directory: str) -> list:
    """
    Scans the directory for PNG files that are eligible for conversion.
    """
    print(f"[*] Scanning directory '{directory}' for PNG files to convert...")
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
        
        if not os.path.isfile(filepath):
            continue
            
        if not filename.lower().endswith(".png"):
            continue
            
        eligible_files.append(filename)
        
    print(f"[+] Found {len(eligible_files)} eligible PNG file(s) for conversion.\n")
    return eligible_files

def main():
    """
    Main execution function. Orchestrates the filtering and conversion
    of PNG files to JPG within the script's directory.
    """
    print("=" * 50)
    print("   Noterun PNG to JPG Converter Script Initialized")
    print("=" * 50)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    files_to_process = filter_eligible_files(script_dir)
    
    if not files_to_process:
        print("[*] No files to process. Exiting.")
        return 0
        
    print("-" * 50)
    
    success_count = 0
    failure_count = 0
    
    for filename in files_to_process:
        filepath = os.path.join(script_dir, filename)
        if convert_image(filepath, script_dir, filename):
            success_count += 1
        else:
            failure_count += 1
            
    print("-" * 50)
    print(f"[*] Conversion process completed.")
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
