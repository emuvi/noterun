# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import urllib.request
import urllib.error
import json
import os
import sys
import glob
import runpy

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

def filter_scripts(contents: list, prefix: str) -> list:
    """
    Filters the repository contents to find files matching the target prefix.
    
    Args:
        contents (list): The list of items from the repository.
        prefix (str): The prefix that target scripts must start with.
        
    Returns:
        list: A list of dictionaries representing the filtered files.
    """
    print(f"[*] Filtering files matching prefix '{prefix}'...")
    filtered_scripts = []
    
    if not isinstance(contents, list):
        print(f"[-] Invalid contents format received from API. Expected a list, got {type(contents).__name__}.")
        return filtered_scripts

    for item in contents:
        # Check if item has expected keys to avoid KeyErrors
        if not isinstance(item, dict) or not all(k in item for k in ("type", "name", "download_url")):
            continue

        if item["type"] == "file" and item["name"].startswith(prefix):
            # Include this script as well — we'll handle self-updates after download
            filtered_scripts.append(item)
            
    print(f"[+] Found {len(filtered_scripts)} script(s) to download.")
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
    if os.path.exists(target_path):
        print(f"[*] File '{file_name}' already exists. Deleting it before download...")
        try:
            os.remove(target_path)
        except OSError as e:
            print(f"[-] Failed to delete existing file '{file_name}': {e}")
            return False

    print(f"[*] Downloading '{file_name}'...")
    try:
        urllib.request.urlretrieve(download_url, target_path)
        print(f"[+] Successfully downloaded '{file_name}'.")
        return True
    except urllib.error.HTTPError as e:
        print(f"[-] HTTP Error {e.code} while downloading '{file_name}': {e.reason}")
    except urllib.error.URLError as e:
        print(f"[-] Network Error while downloading '{file_name}': {e.reason}")
    except OSError as e:
        print(f"[-] File System Error while saving '{file_name}': {e}")
    except Exception as e:
        print(f"[-] An unexpected error occurred while downloading '{file_name}': {e}")
        
    return False

def main():
    """
    Main execution function. Orchestrates the fetching, filtering, and downloading
    of scripts from the GitHub repository.
    """
    print("=" * 50)
    print("   Noterun Scripts Downloader Initialized")
    print("=" * 50)
    
    # Track our own file's modification time to detect updates
    self_path = os.path.abspath(__file__)
    try:
        start_mtime = os.path.getmtime(self_path)
    except OSError:
        start_mtime = None

    contents = fetch_repository_contents(REPO_API_URL)
    
    if not contents:
        print("[-] Aborting download process due to failure in fetching contents.")
        return 1
        
    scripts_to_download = filter_scripts(contents, SCRIPT_PREFIX)
    repo_script_names = {script["name"] for script in scripts_to_download}
    
    script_dir = os.path.dirname(self_path)
    pattern = os.path.join(script_dir, f"{SCRIPT_PREFIX}*.py")
    local_scripts = glob.glob(pattern)
    
    for path in local_scripts:
        name = os.path.basename(path)
        if name not in repo_script_names:
            print(f"[*] Local script '{name}' is not in the repository. Deleting...")
            try:
                os.remove(path)
                print(f"[+] Successfully deleted '{name}'.")
            except OSError as e:
                print(f"[-] Failed to delete '{name}': {e}")
    
    if not scripts_to_download:
        print("[*] No scripts to download. Exiting.")
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
    print(f"[*] Download process completed.")
    print(f"[+] Successful downloads: {success_count}")
    
    if failure_count > 0:
        print(f"[-] Failed downloads: {failure_count}")
        return 1
    else:
        print("[+] All scripts downloaded successfully!")
        # Execute local scripts that match the prefix. If this script was updated
        # during the download process, restart to pick up changes.
        script_dir = os.path.dirname(self_path)
        pattern = os.path.join(script_dir, f"{SCRIPT_PREFIX}*.py")
        local_scripts = sorted(glob.glob(pattern))

        for path in local_scripts:
            try:
                abs_path = os.path.abspath(path)
                name = os.path.basename(path)
                # If this is our own file, check for updates and restart if changed
                if abs_path == self_path:
                    try:
                        cur_mtime = os.path.getmtime(self_path)
                    except OSError:
                        cur_mtime = None

                    if start_mtime is not None and cur_mtime is not None and cur_mtime != start_mtime:
                        print("[*] Detected updated self file on disk. Restarting to apply update...")
                        exec_args = [sys.executable] + sys.argv
                        exec_args = [f'"{arg}"' if ' ' in arg else arg for arg in exec_args]
                        os.execv(sys.executable, exec_args)
                    else:
                        print(f"[*] Skipping execution of self ('{name}') to avoid recursion.")
                    continue

                print(f"[*] Executing local script '{name}'...")
                runpy.run_path(abs_path, run_name="__main__")
                print(f"[+] Finished executing '{name}'.")
            except Exception as e:
                print(f"[-] Error executing '{path}': {e}")

        return 0

if __name__ == "__main__":
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code)
