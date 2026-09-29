# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import sys
import time
import re
from datetime import datetime
import pyperclip

# --- Configuration ---
ENABLE_REPLACEMENTS = True
ENABLE_SEARCH = True

# List of tuples (regex_pattern, replacement_string) for replacements
REGEX_REPLACEMENTS = [
    # Example: Remove leading/trailing whitespaces
    (r"^\s+|\s+$", ""),
    # Example: Replace multiple spaces with a single space
    (r" {2,}", " "),
    # Example: Replace newlines with spaces (uncomment if desired)
    # (r"\r?\n", " "),
]

# List of regex search patterns
REGEX_SEARCHES = [
    # Example: Match URLs
    r"https?://[^\s]+",
    # Example: Match numbers
    # r"\b\d+\b",
]

# Separator for the search results
SEARCH_SEPARATOR = "\n"

OUTPUT_FILENAME_BASE = "cliproc"
OUTPUT_FILE_EXTENSION = ".txt"

# --- Visualization and Logging Helpers ---

def get_current_time() -> str:
    """Returns the current time formatted as HH:MM:SS."""
    try:
        return datetime.now().strftime('%H:%M:%S')
    except Exception as e:
        print(f"🔴 [Error] get_current_time failed: {e}")
        return "00:00:00"

def log_message(message: str) -> None:
    """Logs a general message to the console with a timestamp."""
    try:
        print(f"[{get_current_time()}] ℹ️ [LOG] {message}")
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] log_message failed: {e}")

def print_step(action: str, message: str) -> None:
    """Prints a step being executed with a visual indicator."""
    try:
        print(f"[{get_current_time()}] 🔹 [STEP] [{action}] {message}")
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] print_step failed: {e}")

def print_success(action: str, message: str) -> None:
    """Prints a success message with a visual indicator."""
    try:
        print(f"[{get_current_time()}] ✅ [SUCCESS] [{action}] {message}")
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] print_success failed: {e}")

def print_error(action: str, message: str) -> None:
    """Prints an error message with a visual indicator."""
    try:
        print(f"[{get_current_time()}] 🔴 [ERROR] [{action}] {message}")
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] print_error failed: {e} - message: {message}")

# --- Core Logic ---

def process_text(text: str) -> str:
    """Applies the configured regex replacements to the text."""
    processed = text
    for i, (pattern, repl) in enumerate(REGEX_REPLACEMENTS, 1):
        try:
            processed = re.sub(pattern, repl, processed)
        except re.error as e:
            print_error("Regex Processing", f"Error in regex rule {i} (pattern: {pattern}): {e}")
    return processed

def search_text(text: str) -> str:
    """Searches for all occurrences of the configured regex patterns."""
    found_items = []
    for i, pattern in enumerate(REGEX_SEARCHES, 1):
        try:
            matches = re.findall(pattern, text)
            for match in matches:
                # If pattern has groups, match could be a tuple
                if isinstance(match, tuple):
                    found_items.append(" ".join(str(m) for m in match if m))
                else:
                    found_items.append(str(match))
        except re.error as e:
            print_error("Regex Search", f"Error in regex search {i} (pattern: {pattern}): {e}")
    
    return SEARCH_SEPARATOR.join(found_items)

def save_to_file(text: str, directory: str, counter: int) -> None:
    """Saves the processed text to the output file."""
    filename = f"{OUTPUT_FILENAME_BASE}_{counter:03d}{OUTPUT_FILE_EXTENSION}"
    filepath = os.path.join(directory, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)
        print_success("Save to File", f"Result written to '{filename}'")
    except Exception as e:
        print_error("Save to File", f"Failed to write to file '{filename}': {e}")

def main() -> int:
    current_dir = os.getcwd()
    
    print("=" * 50)
    print("   Noterun Clipboard Watch Script Initialized")
    print("=" * 50)
    print(f"Output files will be saved as: {os.path.join(current_dir, f'{OUTPUT_FILENAME_BASE}_NNN{OUTPUT_FILE_EXTENSION}')}")
    print("Press Ctrl+C to stop.")
    print("-" * 50)
    
    processed_clipboards = set()
    clipboard_counter = 0
    
    # Try to get initial clipboard content so we don't process what's already there
    try:
        initial_content = pyperclip.paste()
        if isinstance(initial_content, str) and initial_content:
            processed_clipboards.add(initial_content)
    except Exception as e:
        print_error("Init Clipboard", f"Could not read initial clipboard: {e}")
    
    waiting = False
    
    try:
        while True:
            try:
                current_clipboard_content = pyperclip.paste()
                
                # Check if it's a string, not empty, and hasn't been processed before
                if isinstance(current_clipboard_content, str) and current_clipboard_content and current_clipboard_content not in processed_clipboards:
                    if waiting:
                        print() # Clear waiting line
                        waiting = False
                        
                    log_message("New clipboard content detected!")
                    
                    processed_text = current_clipboard_content
                    
                    if ENABLE_REPLACEMENTS:
                        print_step("Processing", "Applying regex replacement rules...")
                        processed_text = process_text(processed_text)
                        
                    if ENABLE_SEARCH:
                        print_step("Processing", "Applying regex search rules...")
                        processed_text = search_text(processed_text)
                    
                    if processed_text:
                        clipboard_counter += 1
                        save_to_file(processed_text, current_dir, clipboard_counter)
                    else:
                        print_step("Processing", "Result is empty, no file saved.")
                    
                    processed_clipboards.add(current_clipboard_content)
                    print("-" * 50)
                else:
                    if not waiting:
                        print(f"\r[{get_current_time()}] ⏳ Waiting for clipboard changes... (Checking every 1s)", end="", flush=True)
                        waiting = True
                        
                time.sleep(1.0)
                
            except pyperclip.PyperclipException as e:
                if not waiting:
                    print_error("Clipboard Access", f"Failed to access clipboard: {e}")
                time.sleep(2.0)
            except Exception as e:
                print()
                print_error("Cycle Loop", f"Unexpected error: {e}")
                time.sleep(5.0)
                
    except KeyboardInterrupt:
        print(f"\n[{get_current_time()}] Continuous monitoring stopped by user.")
    
    return 0

if __name__ == '__main__':
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code)
