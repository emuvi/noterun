import urllib.request
import urllib.error
import json
import os
import sys

REPO_API_URL = "https://api.github.com/repos/emuvi/noterun/contents"
SCRIPT_PREFIX = "!-RUN "

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
            # Skip this script itself
            if item["name"] == os.path.basename(__file__):
                print(f"[*] Skipping current script '{item['name']}' to prevent overwrite.")
                continue
            
            filtered_scripts.append(item)
            
    print(f"[+] Found {len(filtered_scripts)} script(s) to download.")
    return filtered_scripts

def download_script(download_url: str, file_name: str) -> bool:
    """
    Downloads a single file from the given URL and saves it locally.
    
    Args:
        download_url (str): The direct download URL of the file.
        file_name (str): The name of the file to save locally.
        
    Returns:
        bool: True if download was successful, False otherwise.
    """
    if os.path.exists(file_name):
        print(f"[*] File '{file_name}' already exists. Deleting it before download...")
        try:
            os.remove(file_name)
        except OSError as e:
            print(f"[-] Failed to delete existing file '{file_name}': {e}")
            return False

    print(f"[*] Downloading '{file_name}'...")
    try:
        urllib.request.urlretrieve(download_url, file_name)
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
    
    contents = fetch_repository_contents(REPO_API_URL)
    
    if not contents:
        print("[-] Aborting download process due to failure in fetching contents.")
        sys.exit(1)
        
    scripts_to_download = filter_scripts(contents, SCRIPT_PREFIX)
    
    if not scripts_to_download:
        print("[*] No scripts to download. Exiting.")
        sys.exit(0)
        
    print("-" * 50)
    
    success_count = 0
    failure_count = 0
    
    for script in scripts_to_download:
        success = download_script(script["download_url"], script["name"])
        if success:
            success_count += 1
        else:
            failure_count += 1
            
    print("-" * 50)
    print(f"[*] Download process completed.")
    print(f"[+] Successful downloads: {success_count}")
    
    if failure_count > 0:
        print(f"[-] Failed downloads: {failure_count}")
        sys.exit(1)
    else:
        print("[+] All scripts downloaded successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()
    input()
