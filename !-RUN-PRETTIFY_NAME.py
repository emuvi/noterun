# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import sys
import re
import datetime
import time
import warnings
from typing import Optional, Any, List, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)


def print_error(message: str) -> None:
    """Prints an error message to stderr."""
    print(message, file=sys.stderr)


try:
    import spacy
except ImportError:
    spacy = None

try:
    from langdetect import detect, LangDetectException
except ImportError:
    detect = None
    LangDetectException = Exception

# Global NLP model cache
_nlp_models = {}

def get_nlp_model(text: str):
    global _nlp_models
    if spacy is None:
        return None

    try:
        lang_code = detect(text) if detect is not None else "pt"
    except Exception:
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
        loaded = None
        try:
            loaded = spacy.load(model_name)
        except Exception:
            try:
                import subprocess
                res = subprocess.run(
                    [sys.executable, "-m", "spacy", "download", model_name],
                    capture_output=True, text=True, encoding="utf-8", errors="replace"
                )
                if res.returncode == 0:
                    loaded = spacy.load(model_name)
            except Exception:
                pass
            if loaded is None:
                for fallback in ("xx_ent_wiki_sm", "pt_core_news_sm", "en_core_web_sm"):
                    if fallback == model_name:
                        continue
                    try:
                        loaded = spacy.load(fallback)
                        break
                    except Exception:
                        continue
        _nlp_models[model_name] = loaded
            
    return _nlp_models[model_name]

def apply_incremental_abbreviation(text: str, nlp_model: Any, limit: int = 100, preserve_first: bool = True) -> str:
    if len(text) <= limit:
        return text

    if nlp_model is None:
        words = text.split()
        for i in range(len(words) - 1, 0 if preserve_first else -1, -1):
            if len(" ".join(words)) <= limit:
                break
            if any(c.isalpha() for c in words[i]) and len(words[i]) > 2:
                words[i] = words[i][0] + "."
        return " ".join(words).strip()

    doc = nlp_model(text)
    
    pieces = []
    candidates_by_phase = {1: [], 2: [], 3: [], 4: []}
    
    first_alpha_idx = -1
    
    for i, token in enumerate(doc):
        word = token.text
        has_alpha = any(c.isalpha() for c in word)
        if has_alpha and first_alpha_idx == -1:
            first_alpha_idx = i
            
        pieces.append({"text": word, "ws": token.whitespace_})
        
        is_candidate = has_alpha and len(word) > 2
        if is_candidate and not (preserve_first and i == first_alpha_idx):
            if token.pos_ in ["ADV"]:
                candidates_by_phase[1].append(i)
            if token.pos_ in ["ADJ", "VERB"]:
                candidates_by_phase[2].append(i)
            if token.pos_ in ["NOUN", "PROPN"]:
                candidates_by_phase[3].append(i)
            
            if token.pos_ in ["ADV", "ADJ", "VERB", "NOUN", "PROPN"]:
                candidates_by_phase[4].append(i)

    def build_string():
        return "".join(p["text"] + p["ws"] for p in pieces).strip()

    current_text = build_string()
    
    for phase in range(1, 5):
        if len(current_text) <= limit:
            return current_text
            
        for i in reversed(candidates_by_phase[phase]):
            if len(current_text) <= limit:
                return current_text
                
            if len(pieces[i]["text"]) > 2:
                pieces[i]["text"] = pieces[i]["text"][0] + "."
                current_text = build_string()
                
    return current_text

def prettify_name_logic(name: str) -> str:
    """
    Applies the prettification logic to a filename string.
    1) If the word is a noun, verb, adjective or adverb, it should have its first letter capitalized and all others lowercase.
    2) All other words should be in lowercase.
    3) The first letter of the full filename must be capitalized.
    """
    # 1. CamelCase splitting: add space between lowercase/number and uppercase
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', name)
    # Add space between uppercase and uppercase followed by lowercase (e.g., XMLParser -> XML Parser)
    name = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', name)
    
    # 2. Replace underscores with spaces while preserving hyphens
    name = name.replace('_', ' ')
    name = " ".join(name.split())
    
    if not name:
        return name

    nlp = get_nlp_model(name)

    if nlp is None:
        minor_words = {"a", "o", "as", "os", "e", "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
                       "por", "para", "com", "sem", "um", "uma", "the", "of", "and", "in", "on", "to", "for", "at", "by"}
        words = name.split()
        formatted = [
            w.capitalize() if (idx == 0 or w.lower() not in minor_words) else w.lower()
            for idx, w in enumerate(words)
        ]
        result = " ".join(formatted).strip()
        if result:
            result = result[0].upper() + result[1:]
        return result
    
    original_text = name
    text_for_nlp = name
    if text_for_nlp.isupper():
        text_for_nlp = text_for_nlp.lower()
        
    doc = nlp(text_for_nlp)
    
    result = ""
    for token in doc:
        word = token.text
        has_alpha = any(c.isalpha() for c in word)

        if has_alpha and token.pos_ in ["NOUN", "PROPN", "VERB", "ADJ", "ADV"]:
            word_fmt = word.capitalize()
        else:
            word_fmt = word.lower()

        result += word_fmt + token.whitespace_
        
    result = result.strip()
    
    if result:
        # 4. The first letter of the full filename must be capitalized.
        result = result[0].upper() + result[1:]
        
    return result

def parse_date_prefix(filename: str) -> Tuple[Optional[datetime.datetime], str, Optional[str]]:
    """
    Attempts to parse date/time prefix from the filename based on known formats.
    """
    english_months = (
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    )
    english_timestamp = re.match(
        r"^([A-Za-z]+)\s+(\d{1,2})\s+(\d{4})\s+(\d{2})-(\d{2})-(\d{2})",
        filename, re.IGNORECASE,
    )
    if english_timestamp:
        try:
            month = english_months.index(english_timestamp.group(1).casefold()) + 1
            day, year, hour, minute, second = map(int, english_timestamp.groups()[1:])
            dt = datetime.datetime(year, month, day, hour, minute, second)
        except ValueError:
            pass
        else:
            rest = filename[english_timestamp.end():]
            for separator, length in ((' - ', 3), ('- ', 2), (' -', 2), (' ', 1), ('-', 1), ('_', 1)):
                if rest.startswith(separator):
                    rest = rest[length:]
                    break
            return dt, rest, "%B %d %Y %H-%M-%S"

    formats = [
        "%Y.%m.%d-%H.%M.%S", "%Y.%m.%d-%H.%M", "%Y.%m.%d_%H.%M.%S", "%Y-%m-%d_%H-%M-%S",
        "%Y.%m.%d %H.%M.%S", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d",
        "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y",
        "%y%m%d_%H%M%S", "%Y%m%d_%H%M%S", "%Y%m%d",
        "%Y.%m.%d %H.%M", "%Y-%m-%d %H.%M", "%Y-%m-%d_%H.%M",
        "%Y%m%d%H%M%S", "%Y%m%d%H%M"
    ]
    
    for length in range(25, 7, -1):
        if length > len(filename):
            continue
        prefix = filename[:length]
        for fmt in formats:
            try:
                dt = datetime.datetime.strptime(prefix, fmt)
                rest = filename[length:]
                
                if rest.startswith(' - '):
                    return dt, rest[3:], fmt
                elif rest.startswith('- ') or rest.startswith(' -'):
                    return dt, rest[2:], fmt
                elif rest.startswith(' ') or rest.startswith('-') or rest.startswith('_'):
                    return dt, rest[1:], fmt
                else:
                    return dt, rest, fmt
            except ValueError:
                continue
    return None, filename, None

def generate_new_filename(filename: str) -> Optional[str]:
    """
    Generates the targeted prettified filename.
    
    Args:
        filename (str): The current name of the file.
        
    Returns:
        str: The newly generated formatted filename, or None if already correctly named.
    """
    name_part, ext = os.path.splitext(filename)
    
    user_prefix_match = re.match(r"^(\[ .*? \] - )(.*)$", name_part)
    if user_prefix_match:
        user_prefix = user_prefix_match.group(1)
        remaining_part = user_prefix_match.group(2)
    else:
        user_prefix = ""
        remaining_part = name_part

    dt, rest_of_name, fmt = parse_date_prefix(remaining_part)
    
    if dt:
        prefix_len = len(remaining_part) - len(rest_of_name)
        prefix = user_prefix + remaining_part[:prefix_len]
        target_name = rest_of_name
    else:
        prefix = user_prefix
        target_name = remaining_part
    
    prettified_name = prettify_name_logic(target_name)
    
    if not prettified_name:
        return None
        
    if len(prettified_name) > 100:
        nlp_model = get_nlp_model(prettified_name)
        prettified_name = apply_incremental_abbreviation(prettified_name, nlp_model, 100)
        
    if len(prettified_name) > 120:
        prettified_name = prettified_name[:120].strip()
        
    new_name = f"{prefix}{prettified_name}{ext}"
    
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

        new_name = re.sub(r'[\\/*?:"<>|]', "", new_name).strip(" .")
        if not new_name:
            return True

        last_error = None
        for attempt in range(1, 4):
            try:
                if filename.lower() == new_name.lower() and filename != new_name:
                    temp_path = os.path.join(directory, new_name + ".noterun_tmp")
                    final_path = os.path.join(directory, new_name)
                    if attempt == 1:
                        print(f"[*] Renaming file...")
                        print(f"    From: '{filename}'")
                        print(f"    To:   '{new_name}'")
                    os.rename(filepath, temp_path)
                    os.rename(temp_path, final_path)
                    print(f"[+] Successfully renamed '{filename}' to '{new_name}'.\n")
                    return True

                new_filepath = get_safe_target_path(directory, new_name)
                final_name = os.path.basename(new_filepath)
                
                if attempt == 1:
                    print(f"[*] Renaming file...")
                    print(f"    From: '{filename}'")
                    print(f"    To:   '{final_name}'")
                
                os.rename(filepath, new_filepath)
                print(f"[+] Successfully renamed '{filename}' to '{final_name}'.\n")
                return True
            except PermissionError as e:
                last_error = f"Permission Denied renaming '{filename}': {e}"
                if attempt < 3:
                    time.sleep(0.4 * attempt)
                    continue
            except OSError as e:
                last_error = f"OS Error renaming '{filename}': {e}"
                if attempt < 3:
                    time.sleep(0.4 * attempt)
                    continue

        print_error(f"[-] {last_error}\n")
        return False
    except Exception as e:
        print_error(f"[-] Unexpected error renaming '{filename}': {e}\n")
        return False

def filter_eligible_files(directory: str) -> tuple:
    """
    Scans the directory for files that are eligible for renaming.
    """
    print(f"[*] Scanning directory '{directory}' for files to rename...")
    eligible_files = []
    
    try:
        files = os.listdir(directory)
    except PermissionError as e:
        print_error(f"[-] Permission Denied accessing directory '{directory}': {e}")
        return [], False
    except Exception as e:
        print_error(f"[-] Unexpected error accessing directory '{directory}': {e}")
        return [], False

    self_name = os.path.basename(__file__)
    self_bat = os.path.splitext(self_name)[0] + ".bat"

    for filename in files:
        filepath = os.path.join(directory, filename)

        try:
            if not os.path.isfile(filepath):
                continue
        except OSError:
            continue

        # Ignore system/script files, hidden files, and common non-target extensions
        if filename.startswith(('!', '_')) or filename in (self_name, self_bat) or filename.lower().endswith(('.py', '.url', '.lnk')):
            continue

        eligible_files.append(filename)
        
    print(f"[+] Found {len(eligible_files)} eligible file(s) for renaming evaluation.\n")
    return eligible_files, True

def main():
    """
    Main execution function. Orchestrates the filtering and prettify renaming
    of files within the script's directory.
    """
    print("=" * 50)
    print("   Noterun Prettify Name Script Initialized")
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
        print_error(f"[-] Errors encountered: {failure_count}")
        return 1
    else:
        print("[+] All files processed without errors!")
        return 0

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
