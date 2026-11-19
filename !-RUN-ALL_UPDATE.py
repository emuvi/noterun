# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import urllib.request
import urllib.error
import json
import os
import sys
import glob
import time

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

REPO_API_URL = "https://api.github.com/repos/emuvi/noterun/contents"
SCRIPT_PREFIX = "!-RUN"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3


def print_error(message: str) -> None:
    """Prints an error message to stderr."""
    print(message, file=sys.stderr)


def fetch_repository_contents(url: str) -> list:
    """
    Fetches the directory contents from the given GitHub repository API URL.
    
    Args:
        url (str): The GitHub API URL for the repository contents.
        
    Returns:
        list: A list of dictionaries representing the contents of the repository.
              Returns an empty list if the request fails.
    """
    print(f"[*] Fetching repository contents from GitHub API...")
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Python-urllib')
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                response_data = response.read().decode('utf-8', errors='replace')
                data = json.loads(response_data)
                print("[+] Successfully retrieved repository contents.")
                return data
        except urllib.error.HTTPError as e:
            last_error = f"HTTP Error {e.code} while fetching repository contents: {e.reason}"
            if 500 <= e.code < 600 and attempt < MAX_RETRIES:
                print(f"[*] Transient HTTP {e.code} (attempt {attempt}/{MAX_RETRIES}). Retrying...")
                time.sleep(attempt * 2)
                continue
            break
        except urllib.error.URLError as e:
            last_error = f"Network Error while reaching GitHub: {e.reason}"
            if attempt < MAX_RETRIES:
                print(f"[*] Transient network error (attempt {attempt}/{MAX_RETRIES}). Retrying...")
                time.sleep(attempt * 2)
                continue
            break
        except json.JSONDecodeError as e:
            last_error = f"Error decoding JSON response from GitHub API: {e}"
            break
        except Exception as e:
            last_error = f"An unexpected error occurred while fetching repository contents: {e}"
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)
                continue
            break

    if last_error:
        print_error(f"[-] {last_error}")
    return []

def filter_scripts(contents: list, prefix: str, local_scripts: set) -> list:
    """
    Filters the repository contents to find files matching the target prefix
    that are also present in the local directory.
    
    Args:
        contents (list): The list of items from the repository.
        prefix (str): The prefix that target scripts must start with.
        local_scripts (set): A set of script filenames currently present in the local directory.
        
    Returns:
        list: A list of dictionaries representing the filtered files to update.
    """
    print(f"[*] Filtering files matching prefix '{prefix}' that exist locally...")
    filtered_scripts = []
    
    if not isinstance(contents, list):
        print_error(f"[-] Invalid contents format received from API. Expected a list, got {type(contents).__name__}.")
        return filtered_scripts

    for item in contents:
        # Check if item has expected keys to avoid KeyErrors
        if not isinstance(item, dict) or not all(k in item for k in ("type", "name", "download_url")):
            continue

        if item["type"] == "file" and item["name"].startswith(prefix) and item["name"] in local_scripts and item.get("download_url"):
            # Include this script for update
            filtered_scripts.append(item)
            
    print(f"[+] Found {len(filtered_scripts)} script(s) to update.")
    return filtered_scripts

def download_script(download_url: str, target_path: str) -> bool:
    """
    Downloads a single file from the given URL and saves it locally.
    
    Args:
        download_url (str): The direct download URL of the file.
        target_path (str): The absolute path where the file should be saved.
        
    Returns:
        bool: True if download was successful, False otherwise.
    """
    file_name = os.path.basename(target_path)

    print(f"[*] Updating '{file_name}'...")
    last_error = None
    new_data = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(download_url)
            req.add_header('User-Agent', 'Python-urllib')
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                new_data = response.read()
            break
        except urllib.error.HTTPError as e:
            last_error = f"HTTP Error {e.code} while updating '{file_name}': {e.reason}"
            if 500 <= e.code < 600 and attempt < MAX_RETRIES:
                print(f"[*] Transient HTTP {e.code} for '{file_name}' (attempt {attempt}/{MAX_RETRIES}). Retrying...")
                time.sleep(attempt * 2)
                continue
            break
        except urllib.error.URLError as e:
            last_error = f"Network Error while updating '{file_name}': {e.reason}"
            if attempt < MAX_RETRIES:
                print(f"[*] Transient network error for '{file_name}' (attempt {attempt}/{MAX_RETRIES}). Retrying...")
                time.sleep(attempt * 2)
                continue
            break
        except Exception as e:
            last_error = f"An unexpected error occurred while updating '{file_name}': {e}"
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)
                continue
            break

    if new_data is None:
        print_error(f"[-] {last_error or f'Failed to update {file_name}'}")
        return False

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if os.path.exists(target_path):
                try:
                    with open(target_path, 'rb') as f:
                        if f.read() == new_data:
                            print(f"[+] File '{file_name}' is already up-to-date. Skipping write.")
                            return True
                except OSError:
                    pass

            with open(target_path, 'wb') as f:
                f.write(new_data)
            print(f"[+] Successfully updated '{file_name}'.")
            return True
        except OSError as e:
            last_error = f"File System Error while saving '{file_name}': {e}"
            if attempt < MAX_RETRIES:
                time.sleep(0.5 * attempt)
                continue
        except Exception as e:
            last_error = f"An unexpected error occurred while saving '{file_name}': {e}"
            break

    print_error(f"[-] {last_error}")
    return False

def main():
    """
    Main execution function. Orchestrates the fetching, filtering, and updating
    of scripts from the GitHub repository for only locally existing scripts.
    """
    print("=" * 50)
    print("   Noterun Local Scripts Updater Initialized")
    print("=" * 50)
    
    script_dir = os.getcwd()
    local_paths = (
        glob.glob(os.path.join(script_dir, f"{SCRIPT_PREFIX}*.py"))
        + glob.glob(os.path.join(script_dir, f"{SCRIPT_PREFIX}*.bat"))
    )
    local_scripts = {os.path.basename(path) for path in local_paths}
    
    print(f"[*] Found {len(local_scripts)} local script(s) matching prefix '{SCRIPT_PREFIX}'.")

    contents = fetch_repository_contents(REPO_API_URL)
    
    if not contents:
        print_error("[-] Aborting update process due to failure in fetching contents.")
        return 1
        
    scripts_to_download = filter_scripts(contents, SCRIPT_PREFIX, local_scripts)
    
    if not scripts_to_download:
        print("[*] No scripts to update. Exiting.")
        return 0
        
    print("-" * 50)
    
    success_count = 0
    failure_count = 0
    
    for script in scripts_to_download:
        target_path = os.path.join(script_dir, script["name"])
        success = download_script(script["download_url"], target_path)
        if success:
            success_count += 1
        else:
            failure_count += 1
            
    print("-" * 50)
    print(f"[*] Update process completed.")
    print(f"[+] Successful updates: {success_count}")
    
    if failure_count > 0:
        print_error(f"[-] Failed updates: {failure_count}")
        return 1
    else:
        print("[+] All existing local scripts updated successfully!")
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
