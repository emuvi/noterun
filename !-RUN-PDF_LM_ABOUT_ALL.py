import importlib
import os
import re
import shutil
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

import PyPDF2
import spacy
from langdetect import detect
from lmstd import ChatResponse, LMStd

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
        print(f"🔴 [ERROR] [get_current_time] get_current_time failed: {e}")
        return "00:00:00"

def log_info(func_name: str, message: str) -> None:
    """
    Logs a general informational message to the console with a timestamp.

    Args:
        func_name (str): The name of the function calling the logger.
        message (str): The message to log.
    """
    try:
        msg = f"[{get_current_time()}] ℹ️ [LOG] [{func_name}] {message}"
        print(msg)
        event_chain.append(msg)
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [ERROR] [log_info] log_info failed: {e}")

def log_step(func_name: str, message: str) -> None:
    """
    Prints a step being executed with a visual indicator.

    Args:
        func_name (str): The name of the function calling the logger.
        message (str): The step message.
    """
    try:
        msg = f"[{get_current_time()}] 🔹 [STEP] [{func_name}] {message}"
        print(msg)
        event_chain.append(msg)
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [ERROR] [log_step] log_step failed: {e}")

def log_success(func_name: str, message: str) -> None:
    """
    Prints a success message with a visual indicator.

    Args:
        func_name (str): The name of the function calling the logger.
        message (str): The success message.
    """
    try:
        msg = f"[{get_current_time()}] ✅ [SUCCESS] [{func_name}] {message}"
        print(msg)
        event_chain.append(msg)
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [ERROR] [log_success] log_success failed: {e}")

def log_error(func_name: str, message: str) -> None:
    """
    Prints an error message with a visual indicator.

    Args:
        func_name (str): The name of the function calling the logger.
        message (str): The error message.
    """
    try:
        msg = f"[{get_current_time()}] 🔴 [ERROR] [{func_name}] {message}"
        print(msg)
        event_chain.append(msg)
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [ERROR] [log_error] log_error failed: {e}")


def print_progress(current: int, total: int, prefix: str = '', suffix: str = '', decimals: int = 1, length: int = 50, fill: str = '█', printEnd: str = "\n") -> None:
    """
    Call in a loop to create terminal progress bar.

    Args:
        current (int): Current iteration.
        total (int): Total iterations.
        prefix (str): Prefix string.
        suffix (str): Suffix string.
        decimals (int): Positive number of decimals in percent complete.
        length (int): Character length of bar.
        fill (str): Bar fill character.
        printEnd (str): End character (e.g. "\r", "\r\n").
    """
    func_name = "print_progress"
    try:
        if total == 0:
            return
        percent = ("{0:." + str(decimals) + "f}").format(100 * (current / float(total)))
        filledLength = int(length * current // total)
        bar = fill * filledLength + '-' * (length - filledLength)
        msg = f'[{get_current_time()}] 🔄 {prefix} |{bar}| {percent}% {suffix}'
        print(msg, end=printEnd)
    except Exception as e:
        log_error(func_name, f"Failed to print progress: {e}")


def print_summary_box(title: str, total: int, success: int, fails: int) -> None:
    """
    Prints a visually clear box summarizing the cycle using Unicode drawing characters.

    Args:
        title (str): The title of the summary box.
        total (int): Total number of items processed.
        success (int): Number of successful operations.
        fails (int): Number of failed operations.
    """
    func_name = "print_summary_box"
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
        log_error(func_name, f"Failed to print summary box: {e}")


def init_lmstd_client() -> Optional[LMStd]:
    """
    Initializes and returns the LM Studio client.

    Returns:
        Optional[LMStd]: Initialized client or None if error.
    """
    func_name = "init_lmstd_client"
    log_step(func_name, "Starting - Parameters: initializing LMStd Client")
    try:
        client = LMStd(
            base_url=os.environ.get("LMSTD_HOST", "http://localhost:1234"),
            api_token=os.environ.get("LMSTD_APIKEY")
        )
        log_success(func_name, "LMStd client initialized successfully.")
        return client
    except Exception as e:
        log_error(func_name, f"Failed to initialize LMStd client: {e}. Check if server is running.")
        return None


def handle_file_error(file_path: str, current_dir: str, error_log: str) -> None:
    """
    Moves the file to '!-ERRORS' to prevent it from being endlessly processed.
    Also attempts to move related files sharing the same basename.
    Saves a detailed log file of the error.

    Args:
        file_path (str): The name of the file that encountered an error.
        current_dir (str): The current working directory.
        error_log (str): The detailed error log to save.
    """
    func_name = "handle_file_error"
    log_step(func_name, f"Starting - Parameters: file_path={file_path}")
    log_step(func_name, f"Moving '{file_path}' to '!-ERRORS'...")
    base_name, ext = os.path.splitext(file_path)
    errors_dir = os.path.join(current_dir, "!-ERRORS")
    os.makedirs(errors_dir, exist_ok=True)
    error_path = os.path.join(errors_dir, file_path)

    try:
        shutil.move(os.path.join(current_dir, file_path), error_path)
        log_success(func_name, f"Moved main file to '!-ERRORS'")
        
        # Save the error log
        log_file_path = os.path.join(errors_dir, f"{base_name}.log")
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(event_chain) + "\n\n[FINAL ERROR]\n" + error_log)
        log_success(func_name, f"Saved error log to '{log_file_path}'")

        # Move related files
        for related_file in os.listdir(current_dir):
            if related_file != file_path and os.path.splitext(related_file)[0] == base_name:
                try:
                    shutil.move(os.path.join(current_dir, related_file),
                                os.path.join(errors_dir, related_file))
                    log_success(func_name, f"Moved related file '{related_file}' to '!-ERRORS'")
                except Exception as e:
                    log_error(func_name, f"Failed to move related file {related_file}: {e}")
    except Exception as e:
        log_error(func_name, f"Failed to move main file {file_path}: {e}")

# --- NLP Functions ---

# Global cache for loaded Spacy models
nlp_models_cache: Dict[str, Any] = {}


def load_spacy_model(lang_code: str) -> Any:
    """
    Loads spacy and the appropriate NLP model based on language.

    Args:
        lang_code (str): The ISO language code (e.g., 'en', 'pt').

    Returns:
        Any: The loaded Spacy NLP model object.
    """
    func_name = "load_spacy_model"
    log_step(func_name, f"Starting - Parameters: lang_code={lang_code}")
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
        log_step(func_name, f"Loading Spacy model '{model_name}' for language '{lang_code}'")

        if model_name in nlp_models_cache:
            log_success(func_name, f"Found in cache: {model_name}")
            return nlp_models_cache[model_name]

        try:
            model_module = importlib.import_module(model_name)
            model = model_module.load()
            nlp_models_cache[model_name] = model
            log_success(func_name, f"Loaded dynamically: {model_name}")
            return model
        except (ImportError, AttributeError):
            model = spacy.load(model_name)
            nlp_models_cache[model_name] = model
            log_success(func_name, f"Loaded via spacy.load: {model_name}")
            return model
    except Exception as e:
        log_error(func_name, f"Error: Spacy model '{model_name}' could not be loaded ({e}).")
        raise RuntimeError(f"Spacy model '{model_name}' not loaded: {e}")


def abbreviate_words(text: str, nlp_model: Any, target_pos: List[str], preserve_first: bool = True) -> str:
    """
    Abbreviates words in text matching specific POS tags.

    Args:
        text (str): The text to abbreviate.
        nlp_model (Any): The Spacy NLP model.
        target_pos (List[str]): List of POS tags to abbreviate.
        preserve_first (bool): Whether to preserve the first word intact.

    Returns:
        str: The abbreviated text.
    """
    func_name = "abbreviate_words"
    log_step(func_name, f"Starting - Parameters: target_pos={target_pos}, preserve_first={preserve_first}")
    try:
        log_step(func_name, "Abbreviating words based on POS tags.")
        if not text or text.upper() == "EMPTY":
            log_success(func_name, "Empty text, nothing to abbreviate.")
            return ""

        doc = nlp_model(text)
        out = ""
        first_alpha_seen = False

        for token in doc:
            word = token.text
            has_alpha = any(c.isalpha() for c in word)

            is_candidate = token.pos_ in target_pos and has_alpha and len(word) > 2

            if has_alpha and preserve_first and not first_alpha_seen:
                is_candidate = False
                first_alpha_seen = True

            if is_candidate:
                out += word[0] + "." + token.whitespace_
            else:
                out += word + token.whitespace_

        res = out.strip()
        log_success(func_name, f"Abbreviated result length: {len(res)}")
        return res
    except Exception as e:
        log_error(func_name, f"Failed to abbreviate words: {e}")
        return text


def apply_abbreviation_phases(summary: str, nlp_model: Any) -> str:
    """
    Applies progressive abbreviation rules to the summary if it exceeds 100 chars.

    Args:
        summary (str): The generated summary string.
        nlp_model (Any): The Spacy NLP model to use for part-of-speech tagging.

    Returns:
        str: The abbreviated summary string.
    """
    func_name = "apply_abbreviation_phases"
    log_step(func_name, "Starting - Parameters: summary evaluation")
    if len(summary) <= 100:
        log_success(func_name, "Summary is within limit, no abbreviation needed.")
        return summary

    log_step(func_name, "Summary > 100 chars. Applying NLP abbreviation phases.")

    # Phase 1: Abbreviate Adverbs (ADV)
    adv_pos = ["ADV"]
    summary = abbreviate_words(summary, nlp_model, adv_pos)
    if len(summary) <= 100:
        log_success(func_name, "Completed at Phase 1.")
        return summary

    # Phase 2: Abbreviate Adjectives and Verbs (ADJ, VERB)
    adj_verb_pos = ["ADJ", "VERB"]
    summary = abbreviate_words(summary, nlp_model, adj_verb_pos)
    if len(summary) <= 100:
        log_success(func_name, "Completed at Phase 2.")
        return summary

    # Phase 3: Abbreviate Nouns and Proper Nouns (NOUN, PROPN)
    noun_pos = ["NOUN", "PROPN"]
    summary = abbreviate_words(summary, nlp_model, noun_pos)
    if len(summary) <= 100:
        log_success(func_name, "Completed at Phase 3.")
        return summary

    # Phase 4: Abbreviate all
    all_pos = ["ADV", "ADJ", "VERB", "NOUN", "PROPN"]
    summary = abbreviate_words(summary, nlp_model, all_pos)

    log_success(func_name, "Completed NLP abbreviation phases (all phases).")
    return summary


def get_pages_to_extract(total_pages: int) -> List[int]:
    """
    Determines which pages to extract from a PDF based on total pages.

    Args:
        total_pages (int): The total number of pages in the document.

    Returns:
        List[int]: A list of page numbers (0-indexed) to extract.
    """
    func_name = "get_pages_to_extract"
    log_step(func_name, f"Starting - Parameters: total_pages={total_pages}")
    pages_to_extract: List[int] = []
    try:
        if total_pages > 33:
            log_step(func_name, "PDF has > 33 pages. Selecting first 11, middle 11, and last 11.")
            mid_start = (total_pages // 2) - 5
            pages_to_extract = sorted(set(
                list(range(11)) +
                list(range(mid_start, mid_start + 11)) +
                list(range(total_pages - 11, total_pages))
            ))
        else:
            log_step(func_name, "PDF has <= 33 pages. Selecting all pages.")
            pages_to_extract = list(range(total_pages))

        log_success(func_name, f"Successfully determined {len(pages_to_extract)} pages to extract.")
        return pages_to_extract
    except Exception as e:
        log_error(func_name, f"Error determining pages to extract: {e}")
        return []


def extract_text_from_pages(reader: PyPDF2.PdfReader, pages_to_extract: List[int]) -> str:
    """
    Extracts text from specified pages of a PDF reader object.

    Args:
        reader (PyPDF2.PdfReader): The PyPDF2 reader instance.
        pages_to_extract (List[int]): The specific page indices to extract.

    Returns:
        str: The extracted text content.
    """
    func_name = "extract_text_from_pages"
    total = len(pages_to_extract)
    log_step(func_name, f"Starting extraction cycle for {total} selected pages.")
    text = ""
    success_count = 0
    fail_count = 0

    try:
        for idx, page_num in enumerate(pages_to_extract):
            try:
                page = reader.pages[page_num]
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
                success_count += 1
            except Exception as page_err:
                log_error(func_name, f"Error extracting text from page {page_num + 1}: {page_err}")
                fail_count += 1

        log_success(func_name, f"Successfully finished text extraction loop. Total characters: {len(text)}")
        return text.strip()
    except Exception as e:
        log_error(func_name, f"Critical error during text extraction loop: {e}")
        return ""


def extract_pdf_text(file_path: str) -> str:
    """
    Opens a PDF file and extracts text content from it.

    Args:
        file_path (str): Path to the PDF file.

    Returns:
        str: The text extracted from the PDF.
    """
    func_name = "extract_pdf_text"
    log_step(func_name, f"Starting - Parameters: file_path='{file_path}'")
    text = ""
    try:
        log_step(func_name, f"Opening file '{file_path}' in binary read mode.")
        with open(file_path, 'rb') as pdf_file:
            log_success(func_name, "File opened successfully.")

            log_step(func_name, "Initializing PyPDF2 PdfReader.")
            reader = PyPDF2.PdfReader(pdf_file)
            total_pages = len(reader.pages)
            log_success(func_name, f"PDF reader initialized successfully. Total pages found: {total_pages}.")

            log_step(func_name, "Calling get_pages_to_extract.")
            pages_to_extract = get_pages_to_extract(total_pages)
            if not pages_to_extract:
                log_error(func_name, "No pages to extract. Aborting extraction.")
                return ""

            log_step(func_name, "Calling extract_text_from_pages.")
            text = extract_text_from_pages(reader, pages_to_extract)
            log_success(func_name, "Text extraction completed.")
    except FileNotFoundError:
        log_error(func_name, f"File not found at '{file_path}'.")
    except PermissionError:
        log_error(func_name, f"Permission denied when accessing '{file_path}'.")
    except Exception as e:
        log_error(func_name, f"Unexpected error reading PDF '{file_path}': {e}")

    return text


def build_summary_prompt(text: str) -> str:
    """
    Builds the prompt string for the LLM to generate a summary.

    Args:
        text (str): The extracted PDF text to summarize.

    Returns:
        str: The formatted prompt for the LLM.
    """
    func_name = "build_summary_prompt"
    log_step(func_name, "Starting - Parameters: text length evaluation")
    prompt = ""
    try:
        log_step(func_name, "Constructing final prompt string.")
        prompt = (
            "Based on the following text extracted from a PDF, tell me what it is about "
            "in a maximum of 100 characters. Be concise and direct, providing only the summary "
            "without conversational filler. Do not use quotes or special characters that "
            "are invalid in filenames. Respond in the exact same language as the provided text, "
            "and ensure perfect spell checking on the language of the document.\n\n"
            f"### TEXT ###\n{text}"
        )
        log_success(func_name, "Prompt built successfully.")
    except Exception as e:
        log_error(func_name, f"Error building prompt: {e}")
    return prompt


def get_summary_from_llm(client: LMStd, prompt: str) -> Optional[str]:
    """
    Calls the Local LM Studio API to get a summary based on the prompt.

    Args:
        client (LMStd): The instantiated LM Studio API client.
        prompt (str): The prompt containing the instructions and text.

    Returns:
        Optional[str]: The summary generated by the LLM, or None if failed.
    """
    func_name = "get_summary_from_llm"
    log_step(func_name, "Starting - Parameters: prompt sent to API")
    content: Optional[str] = None
    try:
        log_step(func_name, "Sending chat request to LM Studio.")
        response: ChatResponse = client.chat(
            system_prompt="You are a helpful assistant that summarizes documents extremely concisely for filenames. Always respond in the same language as the input text and ensure perfect spelling.",
            input_data=prompt,
            temperature=0.0
        )
        log_success(func_name, "Received response from LM Studio.")

        log_step(func_name, "Parsing response output.")
        if "output" in response:
            for item in response.get("output", []):
                if item.get("type") == "message":
                    content = item.get("content")
                    log_success(func_name, "Successfully extracted message content from response.")
                    break

        if not content:
            log_error(func_name, "Model returned an empty or invalid response.")
            return None

        log_success(func_name, f"Final LLM content: {content.strip()}")
        return content.strip()
    except Exception as e:
        log_error(func_name, f"Error calling Local LM Studio API: {e}. Check API settings or server status.")
        return None


def sanitize_filename(summary: str) -> Optional[str]:
    """
    Cleans up the generated summary to be a valid and safe filename.

    Args:
        summary (str): The generated summary string.

    Returns:
        Optional[str]: A sanitized filename string, or None if invalid.
    """
    func_name = "sanitize_filename"
    log_step(func_name, f"Starting - Parameters: summary length {len(summary)}")
    try:
        log_step(func_name, "Removing potential markdown formatting.")
        if summary.startswith("```"):
            summary = summary.split('\n', 1)[-1]
            if summary.endswith("```"):
                summary = summary[:-3]
        summary = summary.strip()

        log_step(func_name, "Enforcing the 100 character limit.")
        if len(summary) > 100:
            summary = summary[:100].strip()

        log_step(func_name, "Replacing invalid characters with underscores.")
        new_base_name = re.sub(r'[\\/*?:"<>|\n\r\t]', "_", summary)

        log_step(func_name, "Removing consecutive underscores and trailing/leading invalid characters.")
        new_base_name = re.sub(r'_{2,}', "_", new_base_name).strip(" _.")

        if not new_base_name:
            log_error(func_name, "Sanitized summary is empty. Cannot use as a filename.")
            return None

        log_success(func_name, f"Successfully sanitized filename base: '{new_base_name}'")
        return new_base_name
    except Exception as e:
        log_error(func_name, f"Error sanitizing filename: {e}")
        return None


def get_unique_new_path(current_dir: str, new_base_name: str, original_path: str) -> Optional[str]:
    """
    Generates a unique file path by appending a counter if the file already exists.

    Args:
        current_dir (str): Directory where the file resides.
        new_base_name (str): Desired new basename.
        original_path (str): The full original path to avoid collisions with itself.

    Returns:
        Optional[str]: A unique file path or None if error.
    """
    func_name = "get_unique_new_path"
    log_step(func_name, f"Starting - Parameters: new_base_name='{new_base_name}'")
    try:
        new_file_name = f"{new_base_name}.pdf"
        new_path = os.path.join(current_dir, new_file_name)

        log_step(func_name, f"Checking if path '{new_path}' already exists.")
        if os.path.exists(new_path) and original_path.lower() != new_path.lower():
            log_step(func_name, "Path already exists. Finding a unique filename with a counter.")
            counter = 2
            while True:
                new_file_name = f"{new_base_name} ({counter}).pdf"
                new_path = os.path.join(current_dir, new_file_name)
                if not os.path.exists(new_path) or original_path.lower() == new_path.lower():
                    log_success(func_name, f"Found unique filename: '{new_file_name}'")
                    break
                counter += 1
        else:
            log_success(func_name, f"Path '{new_path}' is available.")

        return new_path
    except Exception as e:
        log_error(func_name, f"Error generating unique new path: {e}")
        return None


def rename_file(old_path: str, new_path: str) -> bool:
    """
    Renames a file from old_path to new_path.

    Args:
        old_path (str): Original file path.
        new_path (str): Destination file path.

    Returns:
        bool: True if renamed successfully, False otherwise.
    """
    func_name = "rename_file"
    log_step(func_name, f"Attempting to rename '{old_path}' to '{new_path}'.")
    try:
        os.rename(old_path, new_path)
        log_success(func_name, f"Successfully renamed file to '{os.path.basename(new_path)}'.")
        return True
    except FileNotFoundError:
        log_error(func_name, f"Original file '{old_path}' not found for renaming.")
        return False
    except PermissionError:
        log_error(func_name, f"Permission denied when renaming '{old_path}'.")
        return False
    except Exception as e:
        log_error(func_name, f"Error renaming file '{old_path}' to '{new_path}': {e}")
        return False


def rename_associated_files(current_dir: str, old_base_name: str, final_new_base_name: str, new_pdf_name: str) -> None:
    """
    Searches for and renames other files in the directory that share the same old base name.
    Includes a progress cycle.

    Args:
        current_dir (str): Directory where the files reside.
        old_base_name (str): Original base name of the files.
        final_new_base_name (str): New base name to assign.
        new_pdf_name (str): The newly renamed PDF name to avoid renaming it again.
    """
    func_name = "rename_associated_files"
    log_step(func_name, f"Starting - Parameters: old_base_name='{old_base_name}' in '{current_dir}'")
    success_count = 0
    fail_count = 0
    total = 0

    try:
        files_in_dir = os.listdir(current_dir)
        total = len(files_in_dir)
        log_success(func_name, f"Found {total} files in directory. Filtering associated files.")

        for idx, f in enumerate(files_in_dir):
            log_info(func_name, f"Processing associated file check: {f}")
            f_path = os.path.join(current_dir, f)
            try:
                if not os.path.isfile(f_path):
                    continue

                f_base_name, f_ext = os.path.splitext(f)

                # Check if this file is an associated file
                if f_base_name == old_base_name and f != new_pdf_name:
                    log_step(func_name, f"Found associated file: '{f}'")
                    new_f_name = f"{final_new_base_name}{f_ext}"
                    new_f_path = os.path.join(current_dir, new_f_name)

                    log_step(func_name, f"Checking if target path '{new_f_path}' exists.")
                    if os.path.exists(new_f_path):
                        log_error(func_name, f"Cannot rename '{f}' to '{new_f_name}' because target already exists.")
                        fail_count += 1
                        continue

                    log_step(func_name, f"Attempting to rename associated file '{f}' to '{new_f_name}'.")
                    if rename_file(f_path, new_f_path):
                        log_success(func_name, f"Renamed associated file '{f}' to '{new_f_name}'")
                        success_count += 1
                    else:
                        log_error(func_name, f"Failed to rename associated file '{f}'.")
                        fail_count += 1
            except Exception as file_err:
                log_error(func_name, f"Error processing potential associated file '{f}': {file_err}")
                fail_count += 1

        log_success(func_name, "Completed scanning and renaming associated files.")
        if success_count > 0 or fail_count > 0:
            print_summary_box("Associated Files Renaming", success_count + fail_count, success_count, fail_count)

    except Exception as e:
        log_error(func_name, f"Error during associated files renaming process: {e}")


def rename_pdf_from_summary(client: LMStd, file_path: str, pdf_text: str) -> bool:
    """
    Coordinates the process of generating a summary and renaming the PDF and its associated files.

    Args:
        client (LMStd): The instantiated LM Studio API client.
        file_path (str): The original PDF file path.
        pdf_text (str): The extracted text from the PDF.

    Returns:
        bool: True if process was completely successful, False otherwise.
    """
    func_name = "rename_pdf_from_summary"
    log_step(func_name, f"Starting - Parameters: file='{os.path.basename(file_path)}'")

    log_step(func_name, "Calling build_summary_prompt")
    prompt = build_summary_prompt(pdf_text)
    if not prompt:
        log_error(func_name, "Failed to build prompt. Aborting rename process.")
        return False

    log_step(func_name, "Calling get_summary_from_llm")
    summary = get_summary_from_llm(client, prompt)
    if not summary:
        log_error(func_name, "Failed to generate summary. Aborting rename process.")
        return False

    try:
        lang_code = detect(summary)
    except Exception:
        lang_code = "xx"
    current_nlp = load_spacy_model(lang_code)
    summary = apply_abbreviation_phases(summary, current_nlp)

    log_step(func_name, "Calling sanitize_filename")
    new_base_name = sanitize_filename(summary)
    if not new_base_name:
        log_error(func_name, "Failed to sanitize filename. Aborting rename process.")
        return False

    current_dir = os.path.dirname(file_path)

    log_step(func_name, "Calling get_unique_new_path")
    new_path = get_unique_new_path(current_dir, new_base_name, file_path)
    if not new_path:
        log_error(func_name, "Failed to determine a unique new path. Aborting rename process.")
        return False

    old_base_name = os.path.splitext(os.path.basename(file_path))[0]
    new_file_name = os.path.basename(new_path)
    final_new_base_name = os.path.splitext(new_file_name)[0]

    log_step(func_name, f"Ready to rename from '{old_base_name}.pdf' to '{new_file_name}'.")
    success = rename_file(file_path, new_path)

    if success:
        log_success(func_name, "Primary PDF renamed successfully. Proceeding to rename associated files.")
        rename_associated_files(current_dir, old_base_name, final_new_base_name, new_file_name)
        return True
    else:
        log_error(func_name, "Primary PDF renaming failed. Associated files will not be renamed.")
        return False


def process_all_pdfs(client: LMStd) -> None:
    """
    Iterates over all PDF files in the current working directory and processes them.
    Includes a progress cycle.

    Args:
        client (LMStd): The instantiated LM Studio API client.
    """
    func_name = "process_all_pdfs"
    log_step(func_name, "Starting - Parameters: Processing all PDF files")
    success_count = 0
    fail_count = 0
    total = 0

    try:
        log_step(func_name, "Getting current working directory.")
        current_dir = os.getcwd()
        log_success(func_name, f"Current working directory is: {current_dir}")
        log_step(func_name, f"Scanning for PDF files in: {current_dir}")

        try:
            files_in_dir = os.listdir(current_dir)
            pdf_files = [f for f in files_in_dir if f.lower().endswith('.pdf')]
            total = len(pdf_files)
        except Exception as ls_err:
            log_error(func_name, f"Error listing directory contents: {ls_err}")
            return

        if not pdf_files:
            log_error(func_name, "No PDF files found in the current directory. Nothing to do.")
            return

        log_success(func_name, f"Found {total} PDF file(s).")
        log_step("Cycle", f"Processing item 1 of {total}")

        for idx, filename in enumerate(pdf_files):
            event_chain.clear()
            log_step("Cycle", f"Processing item {idx+1} of {total}: {filename}")
            cycle_success = 0
            cycle_fail = 0
            try:
                file_path = os.path.join(current_dir, filename)

                log_step(func_name, "Extracting text from PDF.")
                text = extract_pdf_text(file_path)

                if not text:
                    error_msg = f"Failed to extract text or PDF is empty for: {filename}"
                    log_error(func_name, error_msg)
                    handle_file_error(filename, current_dir, error_msg)
                    fail_count += 1
                    cycle_fail = 1
                else:
                    log_success(func_name, f"Extracted {len(text)} characters of text from '{filename}'.")
                    log_step(func_name, "Proceeding to rename the PDF.")
                    rename_success = rename_pdf_from_summary(client, file_path, text)
                    if rename_success:
                        success_count += 1
                        cycle_success = 1
                        log_success("Cycle", f"Fully processed {filename}")
                    else:
                        error_msg = f"Failed to rename and fully process {filename}"
                        log_error("Cycle", error_msg)
                        handle_file_error(filename, current_dir, error_msg)
                        fail_count += 1
                        cycle_fail = 1

            except Exception as file_err:
                error_msg = f"Unexpected error processing file '{filename}': {file_err}\n{traceback.format_exc()}"
                log_error("Cycle", error_msg)
                handle_file_error(filename, current_dir, error_msg)
                fail_count += 1
                cycle_fail = 1
            
            print_progress(idx + 1, total, prefix='Batch Processing Progress', suffix='Complete', length=30)
            log_info("Cycle", f"Processing: {filename} completed.")

        log_success(func_name, "Batch processing cycle complete.")
        print_summary_box("Processing Summary", total, success_count, fail_count)

    except Exception as e:
        log_error(func_name, f"Critical error during batch processing: {e}")
        print_summary_box("Processing Summary (Interrupted)", total, success_count, fail_count)


def main() -> None:
    """
    Main application entry point.
    """
    func_name = "main"
    log_step(func_name, "Starting - Parameters: Batch PDF Renamer")
    
    client = init_lmstd_client()
    if not client:
        log_error(func_name, "Fatal Error: Could not initialize LMStd Client. Exiting.")
        sys.exit(1)

    try:
        process_all_pdfs(client)
    except Exception as e:
        log_error(func_name, f"Error in main execution block: {e}")
    log_success(func_name, "Batch PDF Renamer finished.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"[{get_current_time()}] 🔴 [ERROR] [main] Process interrupted by user. Exiting.")
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [ERROR] [main] Fatal error: {e}")
