# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import urllib.request
import urllib.error
import json
import os
import sys
import glob

REPO_API_URL = "https://api.github.com/repos/emuvi/noterun/contents"
SCRIPT_PREFIX = "!-RUN"

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
    
    try:
        with urllib.request.urlopen(req) as response:
            response_data = response.read().decode('utf-8')
            data = json.loads(response_data)
            print("[+] Successfully retrieved repository contents.")
            return data
    except urllib.error.HTTPError as e:
        print(f"[-] HTTP Error {e.code} while fetching repository contents: {e.reason}")
    except urllib.error.URLError as e:
        print(f"[-] Network Error while reaching GitHub: {e.reason}")
    except json.JSONDecodeError as e:
        print(f"[-] Error decoding JSON response from GitHub API: {e}")
    except Exception as e:
        print(f"[-] An unexpected error occurred while fetching repository contents: {e}")
    
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
        print(f"[-] Invalid contents format received from API. Expected a list, got {type(contents).__name__}.")
        return filtered_scripts

    for item in contents:
        # Check if item has expected keys to avoid KeyErrors
        if not isinstance(item, dict) or not all(k in item for k in ("type", "name", "download_url")):
            continue

        if item["type"] == "file" and item["name"].startswith(prefix) and item["name"] in local_scripts:
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
    try:
        req = urllib.request.Request(download_url)
        req.add_header('User-Agent', 'Python-urllib')
        with urllib.request.urlopen(req) as response:
            new_data = response.read()
            
        if os.path.exists(target_path):
            with open(target_path, 'rb') as f:
                if f.read() == new_data:
                    print(f"[+] File '{file_name}' is already up-to-date. Skipping write.")
                    return True
            
        with open(target_path, 'wb') as f:
            f.write(new_data)
        print(f"[+] Successfully updated '{file_name}'.")
        return True
    except urllib.error.HTTPError as e:
        print(f"[-] HTTP Error {e.code} while updating '{file_name}': {e.reason}")
    except urllib.error.URLError as e:
        print(f"[-] Network Error while updating '{file_name}': {e.reason}")
    except OSError as e:
        print(f"[-] File System Error while saving '{file_name}': {e}")
    except Exception as e:
        print(f"[-] An unexpected error occurred while updating '{file_name}': {e}")
        
    return False

def main():
    """
    Main execution function. Orchestrates the fetching, filtering, and updating
    of scripts from the GitHub repository for only locally existing scripts.
    """
    print("=" * 50)
    print("   Noterun Local Scripts Updater Initialized")
    print("=" * 50)
    
    self_path = os.path.abspath(__file__)
    script_dir = os.path.dirname(self_path)
    pattern = os.path.join(script_dir, f"{SCRIPT_PREFIX}*.py")
    local_paths = glob.glob(pattern)
    local_scripts = {os.path.basename(path) for path in local_paths}
    
    print(f"[*] Found {len(local_scripts)} local script(s) matching prefix '{SCRIPT_PREFIX}'.")

    contents = fetch_repository_contents(REPO_API_URL)
    
    if not contents:
        print("[-] Aborting update process due to failure in fetching contents.")
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
        print(f"[-] Failed updates: {failure_count}")
        return 1
    else:
        print("[+] All existing local scripts updated successfully!")
        return 0

if __name__ == "__main__":
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code)
