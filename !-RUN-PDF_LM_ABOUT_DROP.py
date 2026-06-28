import os
import sys
import re
import PyPDF2
from datetime import datetime
from typing import Optional, Dict, Any, List
import spacy
from langdetect import detect
import importlib

from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDragEnterEvent, QDropEvent

from lmstd import LMStd, ChatResponse

# Initialize the LM Studio client pointing to the local LM Studio server.
try:
    client = LMStd(base_url=os.environ.get("LMSTD_HOST", "http://localhost:1234"),
                   api_token=os.environ.get("LMSTD_APIKEY"))
except Exception as e:
    print(f"🔴 [Error] Failed to initialize LMStd client: {e}")
    sys.exit(1)


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


def print_step(message: str) -> None:
    """Prints a step in a process."""
    try:
        print(f"[{get_current_time()}] 🔹 [STEP] {message}")
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] print_step failed: {e}")


def print_success(message: str) -> None:
    """Prints a successful step completion."""
    try:
        print(f"[{get_current_time()}] ✅ [SUCCESS] {message}")
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] print_success failed: {e}")


def print_error(message: str) -> None:
    """Prints an error message."""
    try:
        print(f"[{get_current_time()}] 🔴 [ERROR] {message}")
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] print_error failed: {e}")


def print_progress(current: int, total: int, prefix: str = '', suffix: str = '', decimals: int = 1, length: int = 50, fill: str = '█', printEnd: str = "\n") -> None:
    """
    Call in a loop to create terminal progress bar.
    """
    try:
        if total == 0:
            return
        percent = ("{0:." + str(decimals) + "f}").format(100 *
                                                         (current / float(total)))
        filledLength = int(length * current // total)
        bar = fill * filledLength + '-' * (length - filledLength)
        print(
            f'[{get_current_time()}] 🔄 {prefix} |{bar}| {percent}% {suffix}', end=printEnd)
    except Exception as e:
        print_error(f"Failed to print progress: {e}")


def print_summary_box(title: str, total: int, success: int, fails: int) -> None:
    """
    Prints a visually clear box summarizing the cycle.
    """
    try:
        box_width = 50
        print("\n" + "╔" + "═" * (box_width - 2) + "╗")
        title_str = f" 📊 SUMMARY: {title} "
        print("║" + title_str.center(box_width - 2) + "║")
        print("╠" + "═" * (box_width - 2) + "╣")
        print(
            "║" + f" Total Items Processed : {total:<21}".ljust(box_width - 2) + "║")
        print(
            "║" + f" ✅ Successes          : {success:<21}".ljust(box_width - 2) + "║")
        print(
            "║" + f" 🔴 Failures           : {fails:<21}".ljust(box_width - 2) + "║")
        print("╚" + "═" * (box_width - 2) + "╝\n")
    except Exception as e:
        print_error(f"Failed to print summary box: {e}")

# --- NLP Functions ---


# Global cache for loaded Spacy models
nlp_models_cache: Dict[str, Any] = {}


def load_spacy_model(lang_code: str) -> Any:
    """Loads spacy and the appropriate NLP model based on language."""
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
            f"[Load Spacy Model] Loading Spacy model for language '{lang_code}'")

        if model_name in nlp_models_cache:
            print_success(f"[Load Spacy Model] Found in cache: {model_name}")
            return nlp_models_cache[model_name]

        try:
            model_module = importlib.import_module(model_name)
            model = model_module.load()
            nlp_models_cache[model_name] = model
            print_success(
                f"[Load Spacy Model] Loaded dynamically: {model_name}")
            return model
        except (ImportError, AttributeError):
            model = spacy.load(model_name)
            nlp_models_cache[model_name] = model
            print_success(
                f"[Load Spacy Model] Loaded via spacy.load: {model_name}")
            return model
    except Exception as e:
        print_error(f"[Load Spacy Model] Error: {e}")
        print_error(
            f"Error: Spacy model '{model_name}' could not be loaded ({e}).")
        raise RuntimeError(f"Spacy model '{model_name}' not loaded: {e}")


def abbreviate_words(text: str, nlp_model: Any, target_pos: List[str], preserve_first: bool = True) -> str:
    """Abbreviates words in text matching specific POS tags."""
    try:
        print_step("[Abbreviate Words] Abbreviating words based on POS tags.")
        if not text or text.upper() == "EMPTY":
            print_success("[Abbreviate Words] Empty text")
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
        print_success(
            f"[Abbreviate Words] Abbreviated result length: {len(res)}")
        return res
    except Exception as e:
        print_error(f"[Abbreviate Words] Failed to abbreviate words: {e}")
        return text


def apply_abbreviation_phases(summary: str, nlp_model: Any) -> str:
    """Applies progressive abbreviation rules to the summary if it exceeds 180 chars."""
    if len(summary) <= 180:
        return summary

    print_step(
        "[Apply Abbreviation Phases] Summary > 180 chars. Applying NLP abbreviation phases.")

    # Phase 1: Abbreviate Adverbs (ADV)
    adv_pos = ["ADV"]
    summary = abbreviate_words(summary, nlp_model, adv_pos)
    if len(summary) <= 180:
        return summary

    # Phase 2: Abbreviate Adjectives and Verbs (ADJ, VERB)
    adj_verb_pos = ["ADJ", "VERB"]
    summary = abbreviate_words(summary, nlp_model, adj_verb_pos)
    if len(summary) <= 180:
        return summary

    # Phase 3: Abbreviate Nouns and Proper Nouns (NOUN, PROPN)
    noun_pos = ["NOUN", "PROPN"]
    summary = abbreviate_words(summary, nlp_model, noun_pos)
    if len(summary) <= 180:
        return summary

    # Phase 4: Abbreviate all
    all_pos = ["ADV", "ADJ", "VERB", "NOUN", "PROPN"]
    summary = abbreviate_words(summary, nlp_model, all_pos)

    print_success(
        "[Apply Abbreviation Phases] Completed NLP abbreviation phases.")
    return summary


def get_pages_to_extract(total_pages: int) -> List[int]:
    """
    Determines which pages to extract from a PDF based on total pages.
    """
    print_step(
        f"Determining pages to extract for a PDF with {total_pages} total pages.")
    pages_to_extract: List[int] = []
    try:
        if total_pages > 99:
            print_step(
                "PDF has > 99 pages. Selecting first 33, middle 33, and last 33.")
            mid_start = (total_pages // 2) - 16
            pages_to_extract = sorted(set(
                list(range(33)) +
                list(range(mid_start, mid_start + 33)) +
                list(range(total_pages - 33, total_pages))
            ))
        else:
            print_step("PDF has <= 99 pages. Selecting all pages.")
            pages_to_extract = list(range(total_pages))

        print_success(
            f"Successfully determined {len(pages_to_extract)} pages to extract.")
        return pages_to_extract
    except Exception as e:
        print_error(f"Error determining pages to extract: {e}")
        return []


def extract_text_from_pages(reader: PyPDF2.PdfReader, pages_to_extract: List[int]) -> str:
    """
    Extracts text from specified pages of a PDF reader object.
    Includes a progress cycle.
    """
    total = len(pages_to_extract)
    print_step(f"Starting extraction cycle for {total} selected pages.")
    text = ""
    success_count = 0
    fail_count = 0

    try:
        for idx, page_num in enumerate(pages_to_extract):
            print_step(
                f"Extracting text from page {page_num + 1} (Index: {idx+1}/{total})")
            try:
                page = reader.pages[page_num]
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
                success_count += 1
                print_success(f"Extracted page {page_num + 1}")
            except Exception as page_err:
                print_error(
                    f"Error extracting text from page {page_num + 1}: {page_err}")
                fail_count += 1

            print_progress(
                idx + 1, total, prefix='Page Extraction Progress', suffix='Complete', length=30)

        print_success(
            f"Successfully finished text extraction loop. Total characters: {len(text)}")
        print_summary_box("Page Extraction Cycle", total,
                          success_count, fail_count)
        return text.strip()
    except Exception as e:
        print_error(f"Critical error during text extraction loop: {e}")
        print_summary_box("Page Extraction Cycle (Interrupted)",
                          total, success_count, fail_count)
        return ""


def extract_pdf_text(file_path: str) -> str:
    """
    Opens a PDF file and extracts text content from it.
    """
    print_step(f"Starting text extraction for PDF file: '{file_path}'")
    text = ""
    try:
        print_step(f"Opening file '{file_path}' in binary read mode.")
        with open(file_path, 'rb') as pdf_file:
            print_success("File opened successfully.")

            print_step("Initializing PyPDF2 PdfReader.")
            reader = PyPDF2.PdfReader(pdf_file)
            total_pages = len(reader.pages)
            print_success(
                f"PDF reader initialized successfully. Total pages found: {total_pages}.")

            print_step("Calling get_pages_to_extract.")
            pages_to_extract = get_pages_to_extract(total_pages)
            if not pages_to_extract:
                print_error("No pages to extract. Aborting extraction.")
                return ""

            print_step("Calling extract_text_from_pages.")
            text = extract_text_from_pages(reader, pages_to_extract)
            print_success("Text extraction completed.")
    except FileNotFoundError:
        print_error(f"File not found at '{file_path}'.")
    except PermissionError:
        print_error(f"Permission denied when accessing '{file_path}'.")
    except Exception as e:
        print_error(f"Unexpected error reading PDF '{file_path}': {e}")

    return text


def build_summary_prompt(text: str) -> str:
    """
    Builds the prompt string for the LLM to generate a summary.
    """
    print_step("Building the prompt for the LLM.")
    prompt = ""
    try:
        print_step("Truncating text to max 4000 chars.")
        truncated_text = text[:4000]
        print_success(f"Truncated text to {len(truncated_text)} characters.")

        print_step("Constructing final prompt string.")
        prompt = (
            "Based on the following text extracted from a PDF, tell me what it is about "
            "in a maximum of 180 characters. Be concise and direct, providing only the summary "
            "without conversational filler. Do not use quotes or special characters that "
            "are invalid in filenames. Respond in the exact same language as the provided text, "
            "and ensure perfect spell checking on the language of the document.\n\n"
            f"### TEXT ###\n{truncated_text}"
        )
        print_success("Prompt built successfully.")
    except Exception as e:
        print_error(f"Error building prompt: {e}")
    return prompt


def get_summary_from_llm(prompt: str) -> Optional[str]:
    """
    Calls the Local LM Studio API to get a summary based on the prompt.
    """
    print_step("Calling the Local LM Studio API for a summary.")
    content: Optional[str] = None
    try:
        print_step("Sending chat request to LM Studio.")
        response: ChatResponse = client.chat(
            system_prompt="You are a helpful assistant that summarizes documents extremely concisely for filenames. Always respond in the same language as the input text and ensure perfect spelling.",
            input_data=prompt,
            temperature=0.0
        )
        print_success("Received response from LM Studio.")

        print_step("Parsing response output.")
        if "output" in response:
            for item in response.get("output", []):
                if item.get("type") == "message":
                    content = item.get("content")
                    print_success(
                        "Successfully extracted message content from response.")
                    break

        if not content:
            print_error("Model returned an empty or invalid response.")
            return None

        print_success(f"Final LLM content: {content.strip()}")
        return content.strip()
    except Exception as e:
        print_error(f"Error calling Local LM Studio API: {e}")
        return None


def sanitize_filename(summary: str) -> Optional[str]:
    """
    Cleans up the generated summary to be a valid and safe filename.
    """
    print_step("Sanitizing the generated summary for use as a filename.")
    try:
        print_step("Removing potential markdown formatting.")
        if summary.startswith("```"):
            summary = summary.split('\n', 1)[-1]
            if summary.endswith("```"):
                summary = summary[:-3]
        summary = summary.strip()

        print_step("Enforcing the 180 character limit.")
        if len(summary) > 180:
            summary = summary[:180].strip()

        print_step("Replacing invalid characters with underscores.")
        new_base_name = re.sub(r'[\\/*?:"<>|\n\r\t]', "_", summary)

        print_step(
            "Removing consecutive underscores and trailing/leading invalid characters.")
        new_base_name = re.sub(r'_{2,}', "_", new_base_name).strip(" _.")

        if not new_base_name:
            print_error(
                "Sanitized summary is empty. Cannot use as a filename.")
            return None

        print_success(
            f"Successfully sanitized filename base: '{new_base_name}'")
        return new_base_name
    except Exception as e:
        print_error(f"Error sanitizing filename: {e}")
        return None


def get_unique_new_path(current_dir: str, new_base_name: str, original_path: str) -> Optional[str]:
    """
    Generates a unique file path by appending a counter if the file already exists.
    """
    print_step(
        f"Generating a unique new file path for base name '{new_base_name}'.")
    try:
        new_file_name = f"{new_base_name}.pdf"
        new_path = os.path.join(current_dir, new_file_name)

        print_step(f"Checking if path '{new_path}' already exists.")
        if os.path.exists(new_path) and original_path.lower() != new_path.lower():
            print_step(
                "Path already exists. Finding a unique filename with a counter.")
            counter = 2
            while True:
                new_file_name = f"{new_base_name} ({counter}).pdf"
                new_path = os.path.join(current_dir, new_file_name)
                if not os.path.exists(new_path) or original_path.lower() == new_path.lower():
                    print_success(f"Found unique filename: '{new_file_name}'")
                    break
                counter += 1
        else:
            print_success(f"Path '{new_path}' is available.")

        return new_path
    except Exception as e:
        print_error(f"Error generating unique new path: {e}")
        return None


def rename_file(old_path: str, new_path: str) -> bool:
    """
    Renames a file from old_path to new_path.
    """
    print_step(f"Attempting to rename '{old_path}' to '{new_path}'.")
    try:
        os.rename(old_path, new_path)
        print_success(
            f"Successfully renamed file to '{os.path.basename(new_path)}'.")
        return True
    except FileNotFoundError:
        print_error(f"Original file '{old_path}' not found for renaming.")
        return False
    except PermissionError:
        print_error(f"Permission denied when renaming '{old_path}'.")
        return False
    except Exception as e:
        print_error(f"Error renaming file '{old_path}' to '{new_path}': {e}")
        return False


def rename_associated_files(current_dir: str, old_base_name: str, final_new_base_name: str, new_pdf_name: str) -> None:
    """
    Searches for and renames other files in the directory that share the same old base name.
    Includes a progress cycle.
    """
    print_step(
        f"Searching for associated files with base name '{old_base_name}' in '{current_dir}'.")
    success_count = 0
    fail_count = 0
    total = 0

    try:
        files_in_dir = os.listdir(current_dir)
        total = len(files_in_dir)
        print_success(
            f"Found {total} files in directory. Filtering associated files.")

        for idx, f in enumerate(files_in_dir):
            print_step(f"Checking file for association: {f}")
            f_path = os.path.join(current_dir, f)
            try:
                if not os.path.isfile(f_path):
                    continue

                f_base_name, f_ext = os.path.splitext(f)

                # Check if this file is an associated file
                if f_base_name == old_base_name and f != new_pdf_name:
                    print_step(f"Found associated file: '{f}'")
                    new_f_name = f"{final_new_base_name}{f_ext}"
                    new_f_path = os.path.join(current_dir, new_f_name)

                    print_step(
                        f"Checking if target path '{new_f_path}' exists.")
                    if os.path.exists(new_f_path):
                        print_error(
                            f"Cannot rename '{f}' to '{new_f_name}' because target already exists.")
                        fail_count += 1
                        continue

                    print_step(
                        f"Attempting to rename associated file '{f}' to '{new_f_name}'.")
                    if rename_file(f_path, new_f_path):
                        print_success(
                            f"Renamed associated file '{f}' to '{new_f_name}'")
                        success_count += 1
                    else:
                        print_error(f"Failed to rename associated file '{f}'.")
                        fail_count += 1
            except Exception as file_err:
                print_error(
                    f"Error processing potential associated file '{f}': {file_err}")
                fail_count += 1

            print_progress(
                idx + 1, total, prefix='Associated Files Progress', suffix='Complete', length=30)

        print_success("Completed scanning and renaming associated files.")
        if success_count > 0 or fail_count > 0:
            print_summary_box("Associated Files Renaming",
                              success_count + fail_count, success_count, fail_count)

    except Exception as e:
        print_error(f"Error during associated files renaming process: {e}")


def rename_pdf_from_summary(file_path: str, pdf_text: str) -> bool:
    """
    Coordinates the process of generating a summary and renaming the PDF and its associated files.
    """
    print_step(
        f"Starting renaming process for '{os.path.basename(file_path)}'.")

    print_step("Calling build_summary_prompt")
    prompt = build_summary_prompt(pdf_text)
    if not prompt:
        print_error("Failed to build prompt. Aborting rename process.")
        return False

    print_step("Calling get_summary_from_llm")
    summary = get_summary_from_llm(prompt)
    if not summary:
        print_error("Failed to generate summary. Aborting rename process.")
        return False

    try:
        lang_code = detect(summary)
    except Exception:
        lang_code = "xx"
    current_nlp = load_spacy_model(lang_code)
    summary = apply_abbreviation_phases(summary, current_nlp)

    print_step("Calling sanitize_filename")
    new_base_name = sanitize_filename(summary)
    if not new_base_name:
        print_error("Failed to sanitize filename. Aborting rename process.")
        return False

    current_dir = os.path.dirname(file_path)

    print_step("Calling get_unique_new_path")
    new_path = get_unique_new_path(current_dir, new_base_name, file_path)
    if not new_path:
        print_error(
            "Failed to determine a unique new path. Aborting rename process.")
        return False

    old_base_name = os.path.splitext(os.path.basename(file_path))[0]
    new_file_name = os.path.basename(new_path)
    final_new_base_name = os.path.splitext(new_file_name)[0]

    print_step(
        f"Ready to rename from '{old_base_name}.pdf' to '{new_file_name}'.")
    success = rename_file(file_path, new_path)

    if success:
        print_success(
            "Primary PDF renamed successfully. Proceeding to rename associated files.")
        rename_associated_files(
            current_dir, old_base_name, final_new_base_name, new_file_name)
        return True
    else:
        print_error(
            "Primary PDF renaming failed. Associated files will not be renamed.")
        return False


class DropZone(QLabel):
    """A QLabel subclass that accepts PDF file drops."""

    def __init__(self) -> None:
        """Initializes the DropZone widget with styling and drop events enabled."""
        try:
            print_step("Initializing DropZone widget.")
            super().__init__()
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setText("Drag and Drop PDF File Here\n\n🔹 Action: Summarize File\n(Generates a short summary for the filename)")
            self.setStyleSheet('''
                QLabel {
                    border: 4px dashed #aaa;
                    font-size: 24px;
                    color: #555;
                    background-color: #f9f9f9;
                    border-radius: 10px;
                    margin: 20px;
                }
            ''')
            self.setAcceptDrops(True)
            print_success("DropZone widget initialized successfully.")
        except Exception as e:
            print_error(f"Error initializing DropZone: {e}")

    def dragEnterEvent(self, a0: Optional[QDragEnterEvent]) -> None:
        """
        Handles the drag enter event to accept only PDF files.
        """
        try:
            if a0 is None:
                return

            mime_data = a0.mimeData()
            if mime_data is not None and mime_data.hasUrls():
                urls = mime_data.urls()
                if urls and urls[0].toLocalFile().lower().endswith('.pdf'):
                    a0.accept()
                    return
            a0.ignore()
        except Exception as e:
            print_error(f"Error in dragEnterEvent: {e}")
            if a0 is not None:
                a0.ignore()

    def dropEvent(self, a0: Optional[QDropEvent]) -> None:
        """
        Handles the drop event and processes the PDF file.
        """
        try:
            print_step("Drop event triggered.")
            if a0 is None:
                print_error("Received None for dropEvent. Ignoring.")
                return

            mime_data = a0.mimeData()
            if mime_data is not None and mime_data.hasUrls():
                urls = mime_data.urls()
                if urls:
                    file_path = urls[0].toLocalFile()
                    if file_path.lower().endswith('.pdf'):
                        print_success(f"Valid PDF file dropped: {file_path}")
                        self.process_file(file_path)
                    else:
                        print_error(f"Dropped file is not a PDF: {file_path}")
        except Exception as e:
            print_error(f"Error in dropEvent: {e}")

    def process_file(self, file_path: str) -> None:
        """
        Extracts text from the PDF and triggers command execution.
        """
        print_step(
            f"=== Beginning processing cycle for dropped file: {file_path} ===")
        success_count = 0
        fail_count = 0
        total = 1

        try:
            print_step("Attempting to extract text from dropped PDF.")
            text = extract_pdf_text(file_path)

            if not text:
                print_error(
                    "Failed to extract text or PDF is empty. Processing aborted.")
                fail_count += 1
            else:
                print_success(f"Extracted {len(text)} characters of text.")
                print_step("Proceeding to rename the PDF based on summary.")

                rename_success = rename_pdf_from_summary(file_path, text)
                if rename_success:
                    success_count += 1
                    print_success(
                        f"Completed processing for dropped file: {file_path}")
                else:
                    fail_count += 1
                    print_error(f"Failed to rename dropped file: {file_path}")

            print_progress(1, total, prefix='Dropped File Progress',
                           suffix='Complete', length=30)
            print_summary_box("Dropped File Processing Cycle",
                              total, success_count, fail_count)

        except Exception as e:
            print_error(f"Critical error processing dropped file: {e}")
            print_summary_box(
                "Dropped File Processing Cycle (Interrupted)", total, success_count, fail_count)


class MainWindow(QMainWindow):
    """Main application window containing the drop zone."""

    def __init__(self) -> None:
        """Initializes the main window and its layout."""
        try:
            print_step("Initializing MainWindow.")
            super().__init__()
            self.setWindowTitle("PDF Drop & Execute")
            self.resize(600, 400)

            print_step("Setting up central widget and layout.")
            self.central_widget = QWidget()
            self.setCentralWidget(self.central_widget)

            layout = QVBoxLayout()

            self.drop_zone = DropZone()
            layout.addWidget(self.drop_zone)

            self.central_widget.setLayout(layout)
            print_success("MainWindow initialized successfully.")
        except Exception as e:
            print_error(f"Error initializing MainWindow: {e}")


def main() -> None:
    """Main application entry point."""
    print_step("Application entry point reached.")
    try:
        print_step("Initializing QApplication.")
        app = QApplication(sys.argv)

        print_step("Creating MainWindow instance.")
        window = MainWindow()
        window.show()

        print_success(
            "Application started successfully. Waiting for PDF drops...")
        sys.exit(app.exec_())
    except Exception as e:
        print_error(f"Error in main application loop: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_error("Process interrupted by user. Exiting.")
    except Exception as e:
        print_error(f"Fatal error: {e}")
