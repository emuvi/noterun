# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import sys
import re
from typing import Optional
import spacy
from langdetect import detect, LangDetectException

# Global NLP model cache
_nlp_models = {}

def get_nlp_model(text: str):
    global _nlp_models
    try:
        lang_code = detect(text)
    except LangDetectException:
        lang_code = "pt"
        
    spacy_models_map = {
        "pt": "pt_core_news_sm",
        "en": "en_core_web_sm",
        "es": "es_core_news_sm",
        "it": "it_core_news_sm",
        "de": "de_core_news_sm",
        "fr": "fr_core_news_sm",
        "nl": "nl_core_news_sm",
        "el": "el_core_news_sm",
        "ru": "ru_core_news_sm",
        "xx": "xx_ent_wiki_sm"
    }
    
    model_name = spacy_models_map.get(lang_code, "xx_ent_wiki_sm")
    
    if model_name not in _nlp_models:
        try:
            _nlp_models[model_name] = spacy.load(model_name)
        except Exception:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "spacy", "download", model_name])
            _nlp_models[model_name] = spacy.load(model_name)
            
    return _nlp_models[model_name]

def prettify_name_logic(name: str) -> str:
    """
    Applies the prettification logic to a filename string.
    1) If the word is a noun, adjective, or verb, it should have its first letter capitalized and all others lowercase.
    2) If the word is an acronym, it should have all its letters in uppercase.
    3) All other words should be in lowercase.
    4) The first letter of the full filename must be capitalized.
    """
    # 1. CamelCase splitting: add space between lowercase/number and uppercase
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', name)
    # Add space between uppercase and uppercase followed by lowercase (e.g., XMLParser -> XML Parser)
    name = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', name)
    
    # 2. Replace _ and - with spaces
    name = name.replace('_', ' ').replace('-', ' ')
    name = " ".join(name.split())
    
    if not name:
        return name

    nlp = get_nlp_model(name)
    
    original_text = name
    text_for_nlp = name
    if text_for_nlp.isupper():
        text_for_nlp = text_for_nlp.lower()
        
    doc = nlp(text_for_nlp)
    
    result = ""
    for token in doc:
        word = token.text
        original_word = original_text[token.idx : token.idx + len(word)]
        
        has_alpha = any(c.isalpha() for c in word)
        
        is_acronym = False
        if has_alpha and original_word.isupper():
            if not original_text.isupper():
                is_acronym = True
            else:
                vowels = set("aeiouyáéíóúâêôãõ")
                if not any(c.lower() in vowels for c in original_word):
                    is_acronym = True
                    
        if not has_alpha:
            word_fmt = original_word
        elif is_acronym:
            word_fmt = original_word.upper()
        elif token.pos_ in ["NOUN", "PROPN", "ADJ", "VERB", "AUX"]:
            word_fmt = word.capitalize()
        else:
            word_fmt = word.lower()
            
        result += word_fmt + token.whitespace_
        
    result = result.strip()
    
    if result:
        # 4. The first letter of the full filename must be capitalized.
        result = result[0].upper() + result[1:]
        
    return result

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
            print(f"    File: '{filename}'")
            print(f"    Reason: Already perfectly formatted.\n")
            return True

        new_filepath = get_safe_target_path(directory, new_name)
        final_name = os.path.basename(new_filepath)
        
        print(f"[*] Renaming file...")
        print(f"    From: '{filename}'")
        print(f"    To:   '{final_name}'")
        
        os.rename(filepath, new_filepath)
        print(f"[+] Successfully renamed '{filename}' to '{final_name}'.\n")
        return True
        
    except PermissionError as e:
        print(f"[-] Permission Denied renaming '{filename}': {e}\n")
    except OSError as e:
        print(f"[-] OS Error renaming '{filename}': {e}\n")
    except Exception as e:
        print(f"[-] Unexpected error renaming '{filename}': {e}\n")
        
    return False

def filter_eligible_files(directory: str) -> list:
    """
    Scans the directory for files that are eligible for renaming.
    
    Args:
        directory (str): The directory to scan.
        
    Returns:
        list: A list of eligible filenames.
    """
    print(f"[*] Scanning directory '{directory}' for files to rename...")
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
            
        # Ignore system/script files or .py/.url/.lnk files
        if filename.startswith('!-') or filename == os.path.basename(__file__) or filename.lower().endswith(('.py', '.url', '.lnk')):
            continue
            
        eligible_files.append(filename)
        
    print(f"[+] Found {len(eligible_files)} eligible file(s) for renaming evaluation.\n")
    return eligible_files

def main():
    """
    Main execution function. Orchestrates the filtering and prettify renaming
    of files within the script's directory.
    """
    print("=" * 50)
    print("   Noterun Prettify Name Script Initialized")
    print("=" * 50)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    files_to_process = filter_eligible_files(script_dir)
    
    if not files_to_process:
        print("[*] No files to process. Exiting.")
        return 0
        
    print("-" * 50)
    
    success_count = 0
    failure_count = 0
    
    # Sort files to ensure consistent order
    files_to_process.sort()
    
    for filename in files_to_process:
        filepath = os.path.join(script_dir, filename)
            
        if rename_file(filepath, script_dir, filename):
            success_count += 1
        else:
            failure_count += 1
            
    print("-" * 50)
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
