# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import logging
import os
import sys
import re
import time
import warnings
from typing import Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
logging.getLogger("pypdf").setLevel(logging.ERROR)


def print_error(message: str) -> None:
    """Prints an error message to stderr."""
    print(message, file=sys.stderr)


try:
    import pypdf
    from lmstd import LMStd, ChatResponse, ListModelsResponse
except ImportError as e:
    print_error(f"🔴 [Error] Required library missing: {e}. Install with: pip install pypdf lmstd")
    sys.exit(1)

# Initialize the LM Studio client pointing to the local LM Studio server.
# LM Studio runs a local server on http://localhost:1234
try:
    client = LMStd(base_url=os.environ.get("LMSTD_HOST", "http://localhost:1234"),
                   api_token=os.environ.get("LMSTD_APIKEY"))
except Exception as e:
    print_error(f"🔴 [Error] Failed to initialize LMStd client: {e}")
    sys.exit(1)

INSTRUCTION_PROMPT = """You are a fiscal document organization assistant. Your task is to read the provided invoice (nota fiscal) and extract three specific pieces of data to compose the file name.

Extract the following data:
1. Issue Date: Convert to numeric format YYYY-MM-DD (e.g., 2026-04-26).
2. Issuing Company: Identify the trading name or main corporate name. Remove unnecessary legal suffixes (like LTDA, S/A, S.A., ME) and special characters not accepted in file names (like /, \\, :, *, ?, ", <, >, |).
3. Total Value: Find the total value of the invoice and format it using a comma as the decimal separator, with two decimal places (e.g., 150,00 or 1.250,50).

Generate the file name STRICTLY following this pattern:
YYYY-MM-DD - COMPANY - Value

Strict output rules:
- Return ONLY the string with the suggested file name.
- DO NOT include the file extension (e.g., do not put .pdf at the end).
- DO NOT include greetings, explanations, quotes, or any other text before or after the name.
- The COMPANY name must ALWAYS be written in ALL CAPS.

Expected output example:
2026-04-26 - KALUNGA COMÉRCIO E INDÚSTRIA - 345,90
"""

def clean_text_for_llm(value: object) -> str:
    """Normalize text to valid UTF-8 before sending it to the LLM."""
    if value is None:
        return ""

    text = str(value)
    text = text.replace("\ufeff", "")
    text = text.replace("\x00", "")
    text = text.encode("utf-8", errors="replace").decode("utf-8")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch if ch.isprintable() or ch in "\n\t" else " " for ch in text)
    text = re.sub(r"[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_text(file_path: str) -> str:
    """Extract text content from a PDF file resiliently."""
    text = ""
    try:
        with open(file_path, 'rb') as pdf_file:
            reader = pypdf.PdfReader(pdf_file)
            if getattr(reader, "is_encrypted", False):
                try:
                    reader.decrypt("")
                except Exception:
                    pass
            for idx, page in enumerate(reader.pages):
                try:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
                except Exception as page_err:
                    print_error(f"[-] Warning/Error reading page {idx + 1} of {os.path.basename(file_path)}: {page_err}")
    except Exception as e:
        print_error(f"[-] Error reading PDF {file_path}: {e}")
    return clean_text_for_llm(text.strip())

def generate_new_name(pdf_text: str) -> Optional[str]:
    """Generate a new file name using the local AI model via LM Studio with retries."""
    clean_pdf_text = clean_text_for_llm(pdf_text)
    full_prompt = f"{clean_text_for_llm(INSTRUCTION_PROMPT)}\n\nInvoice Text:\n{clean_pdf_text}"
    last_error = None

    for attempt in range(1, 4):
        try:
            response: ChatResponse = client.chat(
                system_prompt=clean_text_for_llm("You are a helpful assistant specialized in formatting filenames."),
                input_data=clean_text_for_llm(full_prompt),
                temperature=0.0,
            )

            content: Optional[str] = None
            if "output" in response:
                for item in response["output"]:
                    if item.get("type") == "message":
                        content = item.get("content")
                        break

            if not content:
                last_error = "no text content returned from model for file."
                if attempt < 3:
                    time.sleep(attempt)
                    continue
                break

            new_name = clean_text_for_llm(content).strip()
            new_name = new_name.replace('\n', '').replace('\r', '').strip('"\' ')
            if new_name.lower().endswith('.pdf'):
                new_name = new_name[:-4]
            new_name = re.sub(r'[\\/*?:"<>|]', "", new_name).strip(" .")
            if new_name:
                return new_name
            last_error = "model returned an empty filename after sanitization."
            break
        except Exception as e:
            last_error = f"Error calling Local LM Studio API: {e}"
            if attempt < 3:
                print(f"[*] Transient LLM error (attempt {attempt}/3). Retrying...")
                time.sleep(attempt * 2)
                continue
            break

    print_error(f"[-] {last_error}")
    return None

def is_already_prefixed(filename: str) -> bool:
    """
    Checks if the filename already matches the target pattern.
    
    Args:
        filename (str): The name of the file to check.
        
    Returns:
        bool: True if already correctly named, False otherwise.
    """
    # Checks the pattern: YYYY-MM-DD - COMPANY - Value.pdf
    # Accepts any text in the middle, and values formatted with comma and optionally dots.
    pattern = r"^\d{4}-\d{2}-\d{2} - .+ - [\d\.,]+\.pdf$"
    return bool(re.match(pattern, filename, re.IGNORECASE))

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
    Handles the AI analysis and renaming operation for a single file.
    
    Args:
        filepath (str): The absolute path to the source file.
        directory (str): The directory of the file.
        filename (str): The current name of the file.
        
    Returns:
        bool: True if renamed or skipped intentionally, False if an error occurred.
    """
    print(f"[*] Extracting text and analyzing '{filename}' with local AI...")
    text = extract_pdf_text(filepath)
    
    if not text:
        print_error(f"[-] Failed: Could not extract text from the PDF '{filename}'.\n")
        return False
        
    # Limit the text length to avoid exceeding the local model's context window
    text = text[:4000]
        
    new_base_name = generate_new_name(text)
    if not new_base_name:
        print_error(f"[-] Failed to generate new name with AI for '{filename}'.\n")
        return False
        
    new_name = f"{new_base_name}.pdf"
    last_error = None

    for attempt in range(1, 4):
        try:
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
        except Exception as e:
            last_error = f"Unexpected error renaming '{filename}': {e}"
            break

    print_error(f"[-] {last_error}\n")
    return False

def filter_eligible_files(directory: str) -> tuple:
    """
    Scans the directory for PDF files that are eligible for renaming.
    """
    print(f"[*] Scanning directory '{directory}' for PDF files to rename...")
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
            
        # Ignore system/script files or .py/.url/.lnk files
        if filename.startswith('!-') or filename.startswith('_') or filename in (self_name, self_bat) or filename.lower().endswith(('.py', '.url', '.lnk')):
            continue
            
        if not filename.lower().endswith('.pdf'):
            continue
            
        eligible_files.append(filename)
        
    print(f"[+] Found {len(eligible_files)} eligible file(s) for renaming evaluation.\n")
    return eligible_files, True

def main():
    """
    Main execution function. Orchestrates the filtering and AI-based renaming
    of invoice PDF files within the script's directory.
    """
    print("=" * 50)
    print("   Noterun Rename Invoice Script Initialized")
    print("=" * 50)
    
    # Check if LM Studio local server is running by attempting to list models
    connected = False
    for attempt in range(1, 3):
        try:
            print("[*] Checking local LM Studio server...")
            _models: ListModelsResponse = client.list_models()
            print("[+] Connection successful!\n")
            connected = True
            break
        except Exception:
            if attempt < 2:
                time.sleep(1.5)
    if not connected:
        print_error("[-] Error: Could not connect to local LM Studio server.")
        print_error("    Please ensure LM Studio is running and the local server is started on http://localhost:1234.")
        return 1

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
        
        if is_already_prefixed(filename):
            print(f"[*] Skipping file...")
            print(f"    File: '{filename}'")
            print(f"    Reason: Already matches the target pattern.\n")
            success_count += 1
            continue
            
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
