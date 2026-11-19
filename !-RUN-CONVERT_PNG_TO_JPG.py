# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import sys
import time
import warnings

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

try:
    from PIL import Image
except ImportError as e:
    print(f"[-] Required library 'Pillow' is not installed: {e}. Install with: pip install Pillow", file=sys.stderr)
    sys.exit(1)


def print_error(message: str) -> None:
    """Prints an error message to stderr."""
    print(message, file=sys.stderr)


# ==============================================================================
# GLOBAL CONFIGURATION
# ==============================================================================
# Determines whether to delete origin files after processing.
# True  -> Deletes the files automatically without asking.
# False -> Keeps the files without asking.
# None  -> Prompts the user to decide.
DELETE_ORIGIN_FILES = None
# ==============================================================================

def convert_image(filepath: str, directory: str, filename: str) -> tuple:
    """
    Handles the operation to convert a single PNG file to JPG.
    """
    jpg_filename = os.path.splitext(filename)[0] + ".jpg"
    jpg_path = os.path.join(directory, jpg_filename)

    if os.path.exists(jpg_path):
        print(f"[*] Skipping file...")
        print(f"    File: '{filename}'")
        print(f"    Reason: Target '{jpg_filename}' already exists\n")
        return True, False

    last_error = None
    for attempt in range(1, 4):
        try:
            if attempt == 1:
                print(f"[*] Converting file...")
                print(f"    From: '{filename}'")
                print(f"    To:   '{jpg_filename}'")

            with Image.open(filepath) as img:
                # Composite alpha transparency onto white background when present
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    try:
                        rgba = img.convert("RGBA")
                        background = Image.new("RGB", rgba.size, (255, 255, 255))
                        background.paste(rgba, mask=rgba.split()[-1])
                        rgb_im = background
                    except Exception:
                        rgb_im = img.convert("RGB")
                else:
                    rgb_im = img.convert("RGB")

                rgb_im.save(jpg_path, quality=95)

            print(f"[+] Successfully converted '{filename}'.\n")
            return True, True
        except PermissionError as e:
            last_error = f"Permission Denied converting '{filename}': {e}"
            if attempt < 3:
                time.sleep(0.4 * attempt)
                continue
        except OSError as e:
            last_error = f"OS Error converting '{filename}': {e}"
            if attempt < 3:
                time.sleep(0.4 * attempt)
                continue
        except Exception as e:
            last_error = f"Unexpected error converting '{filename}': {e}"
            break

    if os.path.exists(jpg_path):
        try:
            os.remove(jpg_path)
        except OSError:
            pass
    print_error(f"[-] {last_error}\n")
    return False, False

def filter_eligible_files(directory: str) -> tuple:
    """
    Scans the directory for PNG files that are eligible for conversion.
    """
    print(f"[*] Scanning directory '{directory}' for PNG files to convert...")
    eligible_files = []
    
    try:
        files = os.listdir(directory)
    except PermissionError as e:
        print_error(f"[-] Permission Denied accessing directory '{directory}': {e}")
        return [], False
    except Exception as e:
        print_error(f"[-] Unexpected error accessing directory '{directory}': {e}")
        return [], False

    for filename in files:
        filepath = os.path.join(directory, filename)
        
        try:
            if not os.path.isfile(filepath):
                continue
        except OSError:
            continue
            
        if not filename.lower().endswith(".png"):
            continue
            
        eligible_files.append(filename)
        
    print(f"[+] Found {len(eligible_files)} eligible PNG file(s) for conversion.\n")
    return eligible_files, True

def main():
    """
    Main execution function. Orchestrates the filtering and conversion
    of PNG files to JPG within the script's directory.
    """
    print("=" * 50)
    print("   Noterun PNG to JPG Converter Script Initialized")
    print("=" * 50)
    
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
    processed_files = []
    
    for filename in files_to_process:
        filepath = os.path.join(script_dir, filename)
        success, converted = convert_image(filepath, script_dir, filename)
        if success:
            success_count += 1
            if converted:
                processed_files.append(filepath)
        else:
            failure_count += 1
            
    print("-" * 50)
    print(f"[*] Conversion process completed.")
    print(f"[+] Processed successfully: {success_count}")
    
    if failure_count > 0:
        print_error(f"[-] Errors encountered: {failure_count}")
    else:
        print("[+] All files processed without errors!")

    if processed_files:
        if DELETE_ORIGIN_FILES is True:
            ans = 'y'
        elif DELETE_ORIGIN_FILES is False:
            ans = 'n'
        else:
            try:
                ans = input("\nDo you want to delete the origin files? (Y/N): ")
            except (EOFError, KeyboardInterrupt):
                ans = 'n'
            
        if ans.strip().lower() == 'y':
            for fp in processed_files:
                deleted = False
                last_err = None
                for attempt in range(1, 4):
                    try:
                        os.remove(fp)
                        print(f"[+] Origin file deleted: {os.path.basename(fp)}")
                        deleted = True
                        break
                    except Exception as e:
                        last_err = e
                        if attempt < 3:
                            time.sleep(0.4 * attempt)
                if not deleted:
                    failure_count += 1
                    print_error(f"[-] Error deleting {os.path.basename(fp)}: {last_err}")

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
