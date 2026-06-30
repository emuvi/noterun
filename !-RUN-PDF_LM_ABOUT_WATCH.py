import glob
import importlib
import os
import re
import shutil
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

import PyPDF2
import spacy
from langdetect import detect
from lmstd import ChatResponse, LMStd
from PyPDF2.errors import PdfReadError

# Global event chain to track execution trace for each file
event_chain: List[str] = []

# --- Visualization and Logging Helpers ---


def get_current_time() -> str:
    """
    Returns the current time formatted as HH:MM:SS.

    Returns:
        str: Formatted current time string.
    """
    try:
        return datetime.now().strftime('%H:%M:%S')
    except Exception as e:
        print(f"🔴 [Error] get_current_time failed: {e}")
        return "00:00:00"


def log_message(message: str) -> None:
    """Logs a general message to the console with a timestamp."""
    try:
        msg = f"[{get_current_time()}] ℹ️ [LOG] {message}"
        print(msg)
        event_chain.append(msg)
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] log_message failed: {e}")


def print_step(action: str, message: str) -> None:
    """Prints a step being executed with a visual indicator."""
    try:
        msg = f"[{get_current_time()}] 🔹 [STEP] [{action}] {message}"
        print(msg)
        event_chain.append(msg)
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] print_step failed: {e}")


def print_success(action: str, message: str) -> None:
    """Prints a success message with a visual indicator."""
    try:
        msg = f"[{get_current_time()}] ✅ [SUCCESS] [{action}] {message}"
        print(msg)
        event_chain.append(msg)
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] print_success failed: {e}")


def print_error(action: str, message: str) -> None:
    """Prints an error message with a visual indicator."""
    try:
        msg = f"[{get_current_time()}] 🔴 [ERROR] [{action}] {message}"
        print(msg)
        event_chain.append(msg)
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] print_error failed: {e} - message: {message}")



def print_summary_box(title: str, total: int, success: int, fails: int) -> None:
    """
    Prints a visually clear box summarizing the cycle.
    """
    try:
        box_width = 50
        lines = [
            "\n" + "╔" + "═" * (box_width - 2) + "╗",
            "║" + f"{title}".center(box_width - 2) + "║",
            "╠" + "═" * (box_width - 2) + "╣",
            "║" + f"Total Processed: {total}".ljust(box_width - 2) + "║",
            "║" + f"Successes:       {success}".ljust(box_width - 2) + "║",
            "║" + f"Failures:        {fails}".ljust(box_width - 2) + "║",
            "╚" + "═" * (box_width - 2) + "╝\n"
        ]
        for line in lines:
            print(line)
        event_chain.extend(lines)
    except Exception as e:
        print_error("Print Summary Box", f"Failed to print summary box: {e}")



# --- NLP Functions ---


# Global cache for loaded Spacy models
nlp_models_cache: Dict[str, Any] = {}
_failed_to_move_files = set()


def load_spacy_model(lang_code: str) -> Any:
    """Loads spacy and the appropriate NLP model based on language."""
    func_name = "Load Spacy Model"
    spacy_models_map: Dict[str, str] = {
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

    try:
        print_step(
            func_name, f"Loading Spacy model for language '{lang_code}'")

        if model_name in nlp_models_cache:
            print_success(func_name, f"Found in cache: {model_name}")
            return nlp_models_cache[model_name]

        try:
            model_module = importlib.import_module(model_name)
            model = model_module.load()
            nlp_models_cache[model_name] = model
            print_success(func_name, f"Loaded dynamically: {model_name}")
            return model
        except (ImportError, AttributeError):
            model = spacy.load(model_name)
            nlp_models_cache[model_name] = model
            print_success(func_name, f"Loaded via spacy.load: {model_name}")
            return model
    except Exception as e:
        print_error(func_name, str(e))
        log_message(
            f"Error: Spacy model '{model_name}' could not be loaded ({e}).")
        raise RuntimeError(f"Spacy model '{model_name}' not loaded: {e}")


def abbreviate_words(text: str, nlp_model: Any, target_pos: List[str], preserve_first: bool = True) -> str:
    """Abbreviates words in text matching specific POS tags."""
    func_name = "Abbreviate Words"
    try:
        print_step(func_name, "Abbreviating words based on POS tags.")
        if not text or text.upper() == "EMPTY":
            print_success(func_name, "Empty text")
            return ""

        doc = nlp_model(text)
        out = ""
        first_alpha_seen = False

        for token in doc:
            word = token.text
            has_alpha = any(c.isalpha() for c in word)

            is_candidate = token.pos_ in target_pos and has_alpha and len(
                word) > 2

            if has_alpha and preserve_first and not first_alpha_seen:
                is_candidate = False
                first_alpha_seen = True

            if is_candidate:
                out += word[0] + "." + token.whitespace_
            else:
                out += word + token.whitespace_

        res = out.strip()
        print_success(func_name, f"Abbreviated result length: {len(res)}")
        return res
    except Exception as e:
        print_error(func_name, f"Failed to abbreviate words: {e}")
        return text


def apply_abbreviation_phases(summary: str, nlp_model: Any) -> str:
    """Applies progressive abbreviation rules to the summary if it exceeds 100 chars."""
    func_name = "Apply Abbreviation Phases"
    if len(summary) <= 100:
        return summary

    print_step(func_name, "Summary > 100 chars. Applying NLP abbreviation phases.")

    # Phase 1: Abbreviate Adverbs (ADV)
    adv_pos = ["ADV"]
    summary = abbreviate_words(summary, nlp_model, adv_pos)
    if len(summary) <= 100:
        return summary

    # Phase 2: Abbreviate Adjectives and Verbs (ADJ, VERB)
    adj_verb_pos = ["ADJ", "VERB"]
    summary = abbreviate_words(summary, nlp_model, adj_verb_pos)
    if len(summary) <= 100:
        return summary

    # Phase 3: Abbreviate Nouns and Proper Nouns (NOUN, PROPN)
    noun_pos = ["NOUN", "PROPN"]
    summary = abbreviate_words(summary, nlp_model, noun_pos)
    if len(summary) <= 100:
        return summary

    # Phase 4: Abbreviate all
    all_pos = ["ADV", "ADJ", "VERB", "NOUN", "PROPN"]
    summary = abbreviate_words(summary, nlp_model, all_pos)

    print_success(func_name, "Completed NLP abbreviation phases.")
    return summary


# --- Client Initialization ---

def init_lmstd_client() -> Optional[LMStd]:
    """
    Initializes and returns the LM Studio client.
    Handles any initialization errors.
    """
    func_name = "Init LMStd Client"
    print_step(func_name, "Starting initialization...")
    try:
        client = LMStd(
            base_url=os.environ.get("LMSTD_HOST", "http://localhost:1234"),
            api_token=os.environ.get("LMSTD_APIKEY")
        )
        print_success(func_name, "LMStd client initialized successfully.")
        return client
    except Exception as e:
        print_error(func_name, f"Failed to initialize LMStd client: {e}")
        return None

# --- PDF Processing Functions ---


def get_pages_to_extract(total_pages: int) -> List[int]:
    """
    Determines which pages to extract from a PDF based on total pages.
    """
    func_name = "Get Pages To Extract"
    print_step(
        func_name, f"Calculating pages to extract for {total_pages} total pages.")
    try:
        if total_pages > 33:
            mid_start = (total_pages // 2) - 5
            pages_to_extract = sorted(set(
                list(range(11)) +
                list(range(mid_start, mid_start + 11)) +
                list(range(total_pages - 11, total_pages))
            ))
            print_success(
                func_name, f"Selected {len(pages_to_extract)} pages (start, middle, end) for large document.")
        else:
            pages_to_extract = list(range(total_pages))
            print_success(
                func_name, f"Selected all {len(pages_to_extract)} pages for small document.")
        return pages_to_extract
    except Exception as e:
        print_error(func_name, f"Unexpected error calculating pages: {e}")
        return []


def extract_pdf_text(file_path: str) -> str:
    """
    Extracts text content from a PDF file using PyPDF2.
    Treats specific errors during reading or parsing.
    """
    func_name = "Extract PDF Text"
    print_step(func_name, f"Opening file '{file_path}'.")
    text = ""
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, 'rb') as pdf_file:
            print_step(func_name, "Reading PDF file structure.")
            reader = PyPDF2.PdfReader(pdf_file)
            total_pages = len(reader.pages)
            pages_to_extract = get_pages_to_extract(total_pages)

            if not pages_to_extract:
                raise ValueError("No pages to extract were determined.")

            print_step(func_name, "Extracting text from selected pages.")
            for i, page_num in enumerate(pages_to_extract):
                try:
                    page = reader.pages[page_num]
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
                except Exception as inner_e:
                    print_error(
                        func_name, f"Failed to extract text from page {page_num}: {inner_e}")

            if text.strip():
                print_success(
                    func_name, "Text successfully extracted from PDF.")
            else:
                print_error(func_name, "Extracted text is empty.")

    except FileNotFoundError as fnf_error:
        print_error(func_name, str(fnf_error))
    except PdfReadError as pdf_error:
        print_error(func_name, f"Invalid or corrupted PDF file: {pdf_error}")
    except Exception as e:
        print_error(
            func_name, f"Unexpected error reading PDF {file_path}: {e}")

    return text.strip()

# --- LLM Functions ---


def build_summary_prompt(text: str) -> str:
    """
    Builds the prompt string for the LLM to generate a summary.
    Truncates the text to avoid exceeding token limits.
    """
    func_name = "Build Summary Prompt"
    print_step(func_name, "Building prompt string...")
    try:
        prompt = (
            "Based on the following text extracted from a PDF, tell me what it is about "
            "in a maximum of 100 characters. Be concise and direct, providing only the summary "
            "without conversational filler. Do not use quotes or special characters that "
            "are invalid in filenames. Respond in the exact same language as the provided text, "
            "and ensure perfect spell checking on the language of the document.\n\n"
            f"### TEXT ###\n{text}"
        )
        print_success(func_name, "Prompt successfully built.")
        return prompt
    except Exception as e:
        print_error(func_name, f"Error building prompt: {e}")
        return ""


def get_summary_from_llm(client: LMStd, prompt: str) -> Optional[str]:
    """
    Calls the Local LM Studio API to get a summary based on the prompt.
    """
    func_name = "Get Summary From LLM"
    print_step(func_name, "Sending prompt to LLM...")
    if not prompt:
        print_error(func_name, "Prompt is empty, aborting LLM call.")
        return None

    try:
        response: ChatResponse = client.chat(
            system_prompt="You are a helpful assistant that summarizes documents extremely concisely for filenames. Always respond in the same language as the input text and ensure perfect spelling.",
            input_data=prompt,
            temperature=0.0
        )
        content: Optional[str] = None
        if "output" in response:
            for item in response.get("output", []):
                if item.get("type") == "message":
                    content = item.get("content")
                    break

        if content:
            result = content.strip()
            print_success(func_name, f"LLM responded: '{result}'")
            return result
        else:
            print_error(
                func_name, "LLM returned an empty or unparseable response.")
            return None
    except ConnectionError:
        print_error(func_name, "Connection error with LM Studio API.")
        return None
    except Exception as e:
        print_error(
            func_name, f"Unexpected error calling Local LM Studio API: {e}")
        return None

# --- File Operations Functions ---


def sanitize_filename(summary: str) -> Optional[str]:
    """
    Cleans up the generated summary to be a valid and safe filename.
    """
    func_name = "Sanitize Filename"
    print_step(func_name, f"Sanitizing string for filename: '{summary}'")
    try:
        if summary.startswith("```"):
            summary = summary.split('\n', 1)[-1]
            if summary.endswith("```"):
                summary = summary[:-3]
        summary = summary.strip()

        if len(summary) > 100:
            summary = summary[:100].strip()

        new_base_name = re.sub(r'[\\/*?:"<>|\n\r\t]', "_", summary)
        new_base_name = re.sub(r'_{2,}', "_", new_base_name).strip(" _.")

        if not new_base_name:
            print_error(
                func_name, "Sanitized filename resulted in an empty string.")
            return None

        print_success(func_name, f"Filename sanitized to: '{new_base_name}'")
        return new_base_name
    except Exception as e:
        print_error(func_name, f"Error sanitizing filename: {e}")
        return None


def get_unique_new_path(current_dir: str, new_base_name: str, original_path: str) -> Optional[str]:
    """
    Generates a unique file path by appending a counter if the file already exists.
    """
    func_name = "Get Unique Path"
    print_step(func_name, f"Generating unique path in '{current_dir}'...")
    try:
        new_file_name = f"{new_base_name}.pdf"
        new_path = os.path.join(current_dir, new_file_name)

        if os.path.exists(new_path) and original_path.lower() != new_path.lower():
            print_step(
                func_name, "Path exists, finding alternative with counter...")
            counter = 2
            while True:
                new_file_name = f"{new_base_name} ({counter}).pdf"
                new_path = os.path.join(current_dir, new_file_name)
                if not os.path.exists(new_path) or original_path.lower() == new_path.lower():
                    break
                counter += 1

        print_success(func_name, f"Unique path generated: '{new_path}'")
        return new_path
    except Exception as e:
        print_error(func_name, f"Error generating unique new path: {e}")
        return None


def handle_file_error(file: str, current_dir: str, error_log: str) -> None:
    """
    Moves the file to '!-ERRORS' to prevent it from being endlessly processed.
    Also attempts to move related files sharing the same basename.
    Saves a detailed log file of the error.
    """
    global _failed_to_move_files
    func_name = "Move On Error"
    print_step(
        func_name, f"Moving '{file}' to '!-ERRORS'")
    try:
        base_name, ext = os.path.splitext(file)
        errors_dir = os.path.join(current_dir, "!-ERRORS")
        os.makedirs(errors_dir, exist_ok=True)
        error_path = os.path.join(errors_dir, file)

        if not os.path.exists(file):
            raise FileNotFoundError(f"Original file missing: {file}")

        shutil.move(file, error_path)
        print_success(func_name, f"Moved main file to '!-ERRORS'")

        # Save the error log
        log_file_path = os.path.join(errors_dir, f"{base_name}.log")
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(event_chain) + "\n\n[FINAL ERROR]\n" + error_log)
        print_success(func_name, f"Saved error log to '{log_file_path}'")

        # Move related files
        for related_file in os.listdir(current_dir):
            if related_file != file and os.path.splitext(related_file)[0] == base_name:
                try:
                    rel_error_path = os.path.join(errors_dir, related_file)
                    shutil.move(related_file, rel_error_path)
                    print_success(func_name, f"Moved related file '{related_file}' to '!-ERRORS'")
                except Exception as inner_e:
                    print_error(
                        func_name, f"Failed to move related file {related_file}: {inner_e}")

    except FileNotFoundError as fnfe:
        print_error(func_name, str(fnfe))
        _failed_to_move_files.add(file)
    except Exception as e:
        print_error(
            func_name, f"Failed to move main file {file}: {e}")
        _failed_to_move_files.add(file)


def rename_file(old_path: str, new_path: str) -> bool:
    """
    Renames/Moves a file from old_path to new_path.
    """
    func_name = "Rename File"
    print_step(func_name, f"Attempting to rename '{old_path}' to '{new_path}'.")
    try:
        shutil.move(old_path, new_path)
        print_success(func_name, f"Successfully renamed file to '{os.path.basename(new_path)}'.")
        return True
    except FileNotFoundError:
        print_error(func_name, f"Original file '{old_path}' not found for renaming.")
        return False
    except PermissionError:
        print_error(func_name, f"Permission denied when renaming '{old_path}'.")
        return False
    except Exception as e:
        print_error(func_name, f"Error renaming file '{old_path}' to '{new_path}': {e}")
        return False


def rename_associated_files(current_dir: str, target_dir: str, old_base_name: str, final_new_base_name: str, new_pdf_name: str) -> None:
    """
    Searches for and renames other files in the directory that share the same old base name.
    Includes a progress cycle.
    """
    func_name = "Rename Associated Files"
    print_step(func_name, f"Searching for associated files with base name '{old_base_name}' in '{current_dir}'.")
    success_count = 0
    fail_count = 0
    total = 0

    try:
        files_in_dir = os.listdir(current_dir)
        total = len(files_in_dir)
        print_success(func_name, f"Found {total} files in directory. Filtering associated files.")

        for idx, f in enumerate(files_in_dir):
            print_step(func_name, f"Checking file for association: {f}")
            f_path = os.path.join(current_dir, f)
            try:
                if not os.path.isfile(f_path):
                    continue

                f_base_name, f_ext = os.path.splitext(f)

                # Check if this file is an associated file
                if f_base_name == old_base_name and f != new_pdf_name:
                    print_step(func_name, f"Found associated file: '{f}'")
                    new_f_name = f"{final_new_base_name}{f_ext}"
                    new_f_path = os.path.join(target_dir, new_f_name)

                    print_step(func_name, f"Checking if target path '{new_f_path}' exists.")
                    if os.path.exists(new_f_path):
                        print_error(func_name, f"Cannot rename '{f}' to '{new_f_name}' because target already exists.")
                        fail_count += 1
                        continue

                    print_step(func_name, f"Attempting to rename associated file '{f}' to '{new_f_name}'.")
                    if rename_file(f_path, new_f_path):
                        print_success(func_name, f"Renamed associated file '{f}' to '{new_f_name}'")
                        success_count += 1
                    else:
                        print_error(func_name, f"Failed to rename associated file '{f}'.")
                        fail_count += 1
            except Exception as file_err:
                print_error(func_name, f"Error processing potential associated file '{f}': {file_err}")
                fail_count += 1

        print_success(func_name, "Completed scanning and renaming associated files.")
        if success_count > 0 or fail_count > 0:
            print_summary_box("Associated Files Renaming", success_count + fail_count, success_count, fail_count)

    except Exception as e:
        print_error(func_name, f"Error during associated files renaming process: {e}")


def get_files_to_process() -> List[str]:
    """
    Retrieves a list of PDF files that need to be processed in the current directory.
    Ignores files with special suffixes.
    """
    func_name = "Get Files To Process"
    print_step(func_name, "Scanning directory for valid PDFs...")
    try:
        pdf_files = sorted(glob.glob("*.pdf"))
        files_to_process = []
        for f in pdf_files:
            if f.upper().startswith("RAND"):
                continue
            if f in _failed_to_move_files:
                continue
            files_to_process.append(f)
        print_success(
            func_name, f"Found {len(files_to_process)} files to process.")
        return files_to_process
    except Exception as e:
        print_error(func_name, f"Error scanning for files: {e}")
        return []

# --- Main Logic ---


def process_single_file(client: LMStd, file: str, current_dir: str) -> bool:
    """
    Processes a single PDF file: reads, summarizes, and renames it.
    Returns True if fully successful, False otherwise.
    """
    event_chain.clear()
    msg = f"\n--- Processing File: {file} ---"
    print(msg)
    event_chain.append(msg)

    text = extract_pdf_text(file)
    if not text:
        handle_file_error(file, current_dir, "Failed to extract text or PDF is empty.")
        return False

    prompt = build_summary_prompt(text)
    if not prompt:
        handle_file_error(file, current_dir, "Failed to build summary prompt.")
        return False

    start_time = time.time()
    llm_response = get_summary_from_llm(client, prompt)
    elapsed_time = time.time() - start_time
    print_success("LLM Timing", f"LLM call completed in {elapsed_time:.2f}s")

    if not llm_response:
        handle_file_error(file, current_dir, "LLM returned an empty or unparseable response.")
        return False

    try:
        lang_code = detect(llm_response)
    except Exception:
        lang_code = "xx"
    current_nlp = load_spacy_model(lang_code)
    llm_response = apply_abbreviation_phases(llm_response, current_nlp)

    new_base_name = sanitize_filename(llm_response)
    if not new_base_name:
        handle_file_error(file, current_dir, "Sanitized filename resulted in an empty string.")
        return False

    target_dir = os.path.dirname(current_dir)
    new_path = get_unique_new_path(target_dir, new_base_name, file)
    if not new_path:
        handle_file_error(file, current_dir, "Failed to generate unique new path.")
        return False

    old_base_name = os.path.splitext(os.path.basename(file))[0]
    new_file_name = os.path.basename(new_path)
    final_new_base_name = os.path.splitext(new_file_name)[0]

    print_step("Rename Process", f"Ready to rename from '{old_base_name}.pdf' to '{new_file_name}'.")
    success = rename_file(os.path.join(current_dir, file), new_path)

    if success:
        print_success("Rename Process", "Primary PDF renamed successfully. Proceeding to rename associated files.")
        rename_associated_files(current_dir, target_dir, old_base_name, final_new_base_name, new_file_name)
    else:
        print_error("Rename Process", "Primary PDF renaming failed. Associated files will not be renamed.")
        handle_file_error(file, current_dir, "Failed to rename main PDF and associated files.")
        return False

    return True


def main() -> None:
    current_dir = os.getcwd()

    print("==========================================================================================")
    print("This script will continuously monitor the current folder for new PDF files (excluding 'RAND*')")
    print("to summarize their content and rename them (and their sidecar files).")
    print("==========================================================================================")
    proceed = input("Do you want to proceed? (yes/no): ").strip().lower()
    if proceed != 'yes':
        log_message("Operation canceled.")
        return

    client = init_lmstd_client()
    if not client:
        log_message("Fatal Error: Could not initialize LMStd Client. Exiting.")
        sys.exit(1)

    log_message("Starting continuous summary watcher. Press Ctrl+C to stop.")
    print("-" * 90)

    total_session_success = 0
    total_session_fails = 0

    try:
        waiting = False

        while True:
            try:
                # 1. Fetch files
                files_to_process = get_files_to_process()

                if not files_to_process:
                    if not waiting:
                        print(
                            f"\r[{get_current_time()}] ⏳ Waiting for new PDF files... (Checking every 5s)", end="", flush=True)
                        waiting = True
                    time.sleep(5)
                    continue

                if waiting:
                    print()  # Break the inline wait message
                    waiting = False

                # 2. Process files in this cycle
                cycle_total = len(files_to_process)
                cycle_success = 0
                cycle_fails = 0

                print(
                    f"\n[{get_current_time()}] ---> STARTING NEW CYCLE: {cycle_total} files to process <---")

                for index, file in enumerate(files_to_process):
                    file_success = 0
                    file_fail = 0
                    try:
                        # Progress percentage
                        progress_pct = ((index) / cycle_total) * 100
                        print(
                            f"\n>> Cycle Progress: {progress_pct:.1f}% ({index}/{cycle_total})")

                        # Process individual file
                        success = process_single_file(
                            client, file, current_dir)
                        if success:
                            cycle_success += 1
                            total_session_success += 1
                            file_success = 1
                        else:
                            cycle_fails += 1
                            total_session_fails += 1
                            file_fail = 1

                    except Exception as e:
                        error_msg = f"Unexpected error while processing file '{file}': {e}\n{traceback.format_exc()}"
                        print_error("Main Loop", error_msg)
                        handle_file_error(file, current_dir, error_msg)
                        cycle_fails += 1
                        total_session_fails += 1
                        file_fail = 1
                    
                    print_summary_box(
                        title=f"Cycle Summary",
                        total=1,
                        success=file_success,
                        fails=file_fail
                    )
                    print_summary_box(
                        title=f"Overall Session Summary",
                        total=total_session_success + total_session_fails,
                        success=total_session_success,
                        fails=total_session_fails
                    )

                # End of file loop - 100% progress
                print(
                    f"\n>> Cycle Progress: 100.0% ({cycle_total}/{cycle_total})")

                # 3. Print summaries
                if cycle_total > 0:
                    print_summary_box(
                        title=f"Overall Session Summary",
                        total=total_session_success + total_session_fails,
                        success=total_session_success,
                        fails=total_session_fails
                    )
                    print(
                        f"[{get_current_time()}] Cycle completed. Pausing before next check...")

                time.sleep(2)

            except Exception as e:
                print_error(
                    "Main Loop", f"Unexpected error in the main cycle loop: {e}")
                traceback.print_exc()
                time.sleep(5)

    except KeyboardInterrupt:
        print(f"\n[{get_current_time()}] Continuous monitoring stopped by user.")
        print_summary_box(
            title="Final Overall Session Summary",
            total=total_session_success + total_session_fails,
            success=total_session_success,
            fails=total_session_fails
        )


if __name__ == "__main__":
    main()
