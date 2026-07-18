# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import sys
import re
import PyPDF2
from typing import Optional
from lmstd import LMStd, ChatResponse, ListModelsResponse

# Initialize the LM Studio client pointing to the local LM Studio server.
# LM Studio runs a local server on http://localhost:1234
client = LMStd(base_url="http://localhost:1234", api_token=os.environ.get("LMSTD_APIKEY"))

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

def extract_pdf_text(file_path: str) -> str:
    """Extract text content from a PDF file."""
    text = ""
    try:
        with open(file_path, 'rb') as pdf_file:
            reader = PyPDF2.PdfReader(pdf_file)
            for page in reader.pages:
                text += page.extract_text() + "\n"
    except Exception as e:
        print(f"[-] Error reading PDF {file_path}: {e}")
    return text.strip()

def generate_new_name(pdf_text: str) -> Optional[str]:
    """Generate a new file name using the local AI model via LM Studio."""
    full_prompt = f"{INSTRUCTION_PROMPT}\n\nInvoice Text:\n{pdf_text}"
    try:
        # Call LM Studio's chat endpoint via the local client
        response: ChatResponse = client.chat(
            system_prompt="You are a helpful assistant specialized in formatting filenames.",
            input_data=full_prompt,
            temperature=0.0,
        )

        # Extract the model's text content using lmstd types.
        content: Optional[str] = None
        if "output" in response:
            for item in response["output"]:
                if item.get("type") == "message":
                    content = item.get("content")
                    break

        if not content:
            print(f"[-] Error: no text content returned from model for file.")
            return None

        new_name = content.strip()
        # Clear line breaks that the model might have accidentally returned
        new_name = new_name.replace('\n', '').replace('\r', '')
        
        # Ensure the model did not insert the extension
        if new_name.lower().endswith('.pdf'):
            new_name = new_name[:-4]
            
        # Remove invalid Windows characters that might have slipped through
        new_name = re.sub(r'[\\/*?:"<>|]', "", new_name)
        
        return new_name
    except Exception as e:
        print(f"[-] Error calling Local LM Studio API: {e}")
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
        print(f"[-] Failed: Could not extract text from the PDF.\n")
        return False
        
    # Limit the text length to avoid exceeding the local model's context window
    text = text[:4000]
        
    new_base_name = generate_new_name(text)
    if not new_base_name:
        print(f"[-] Failed to generate new name with AI.\n")
        return False
        
    new_name = f"{new_base_name}.pdf"
    
    try:
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
    Scans the directory for PDF files that are eligible for renaming.
    
    Args:
        directory (str): The directory to scan.
        
    Returns:
        list: A list of eligible filenames.
    """
    print(f"[*] Scanning directory '{directory}' for PDF files to rename...")
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
        if filename.startswith('!-') or filename.startswith('_') or filename == os.path.basename(__file__) or filename.lower().endswith(('.py', '.url', '.lnk')):
            continue
            
        if not filename.lower().endswith('.pdf'):
            continue
            
        eligible_files.append(filename)
        
    print(f"[+] Found {len(eligible_files)} eligible file(s) for renaming evaluation.\n")
    return eligible_files

def main():
    """
    Main execution function. Orchestrates the filtering and AI-based renaming
    of invoice PDF files within the script's directory.
    """
    print("=" * 50)
    print("   Noterun Rename Invoice Script Initialized")
    print("=" * 50)
    
    # Check if LM Studio local server is running by attempting to list models
    try:
        print("[*] Checking local LM Studio server...")
        _models: ListModelsResponse = client.list_models()
        print("[+] Connection successful!\n")
    except Exception:
        print("[-] Error: Could not connect to local LM Studio server.")
        print("    Please ensure LM Studio is running and the local server is started on http://localhost:1234.")
        return 1

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
        print(f"[-] Errors encountered: {failure_count}")
        return 1
    else:
        print("[+] All files processed without errors!")
        return 0

if __name__ == '__main__':
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code)
