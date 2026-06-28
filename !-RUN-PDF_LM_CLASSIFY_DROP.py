import os
import sys
import re
import shutil
import unicodedata
import traceback
import PyPDF2
from datetime import datetime
from typing import Optional, Dict, Any, List

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
        percent = ("{0:." + str(decimals) + "f}").format(100 * (current / float(total)))
        filledLength = int(length * current // total)
        bar = fill * filledLength + '-' * (length - filledLength)
        print(f'[{get_current_time()}] 🔄 {prefix} |{bar}| {percent}% {suffix}', end=printEnd)
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
        print("║" + f" Total Items Processed : {total:<21}".ljust(box_width - 2) + "║")
        print("║" + f" ✅ Successes          : {success:<21}".ljust(box_width - 2) + "║")
        print("║" + f" 🔴 Failures           : {fails:<21}".ljust(box_width - 2) + "║")
        print("╚" + "═" * (box_width - 2) + "╝\n")
    except Exception as e:
        print_error(f"Failed to print summary box: {e}")


def get_classify_prompt(parent_dir: str, current_dir: str) -> str:
    """Generates the prompt instruction dynamically based on parent directory folders."""
    print_step("Scanning target categories in parent directory...")

    prompt = (
        "Você é um especialista em classificação de documentos e arquivologia.\n"
        "Sua tarefa é analisar o documento fornecido e classificá-lo em EXATAMENTE UMA das categorias listadas.\n\n"
        "### CATEGORIAS DISPONÍVEIS ###\n"
    )

    try:
        current_dir_name = os.path.basename(current_dir)
        dirs = []
        for entry in os.listdir(parent_dir):
            full_path = os.path.join(parent_dir, entry)
            if os.path.isdir(full_path):
                if entry != current_dir_name:
                    dirs.append(entry)

        if not dirs:
            print_error("No category folders found in the parent directory.")
            return ""

        for d in sorted(dirs):
            prompt += f"- {d}\n"

        print_success(f"Found {len(dirs)} category folders to use in prompt.")

    except Exception as e:
        print_error(f"Error reading parent directory to generate prompt: {e}")
        return ""

    prompt += (
        "\n### INSTRUÇÕES CRÍTICAS ###\n"
        "1. Analise o tema principal e o conteúdo do documento com cuidado.\n"
        "2. Escolha a categoria da lista acima que melhor descreve o documento.\n"
        "3. Sua resposta DEVE SER APENAS O NOME EXATO DA CATEGORIA. Não inclua absolutamente mais nada.\n"
        "4. NÃO forneça justificativas, NÃO escreva frases como 'A categoria é', e NÃO coloque pontos finais após o nome.\n"
    )
    return prompt


def get_pages_to_extract(total_pages: int) -> List[int]:
    """Determines which pages to extract from a PDF based on total pages."""
    print_step(f"Determining pages to extract for a PDF with {total_pages} total pages.")
    pages_to_extract: List[int] = []
    try:
        if total_pages > 99:
            print_step("PDF has > 99 pages. Selecting first 33, middle 33, and last 33.")
            mid_start = (total_pages // 2) - 16
            pages_to_extract = sorted(set(
                list(range(33)) +
                list(range(mid_start, mid_start + 33)) +
                list(range(total_pages - 33, total_pages))
            ))
        else:
            print_step("PDF has <= 99 pages. Selecting all pages.")
            pages_to_extract = list(range(total_pages))

        print_success(f"Successfully determined {len(pages_to_extract)} pages to extract.")
        return pages_to_extract
    except Exception as e:
        print_error(f"Error determining pages to extract: {e}")
        return []


def extract_text_from_pages(reader: PyPDF2.PdfReader, pages_to_extract: List[int]) -> str:
    """Extracts text from specified pages of a PDF reader object."""
    total = len(pages_to_extract)
    print_step(f"Starting extraction cycle for {total} selected pages.")
    text = ""
    success_count = 0
    fail_count = 0

    try:
        for idx, page_num in enumerate(pages_to_extract):
            print_step(f"Extracting text from page {page_num + 1} (Index: {idx+1}/{total})")
            try:
                page = reader.pages[page_num]
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
                success_count += 1
                print_success(f"Extracted page {page_num + 1}")
            except Exception as page_err:
                print_error(f"Error extracting text from page {page_num + 1}: {page_err}")
                fail_count += 1

            print_progress(idx + 1, total, prefix='Page Extraction Progress', suffix='Complete', length=30)

        print_success(f"Successfully finished text extraction loop. Total characters: {len(text)}")
        print_summary_box("Page Extraction Cycle", total, success_count, fail_count)
        return text.strip()
    except Exception as e:
        print_error(f"Critical error during text extraction loop: {e}")
        print_summary_box("Page Extraction Cycle (Interrupted)", total, success_count, fail_count)
        return ""


def extract_pdf_text(file_path: str) -> str:
    """Opens a PDF file and extracts text content from it."""
    print_step(f"Starting text extraction for PDF file: '{file_path}'")
    text = ""
    try:
        print_step(f"Opening file '{file_path}' in binary read mode.")
        with open(file_path, 'rb') as pdf_file:
            print_success("File opened successfully.")

            print_step("Initializing PyPDF2 PdfReader.")
            reader = PyPDF2.PdfReader(pdf_file)
            total_pages = len(reader.pages)
            print_success(f"PDF reader initialized successfully. Total pages found: {total_pages}.")

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


def query_model_classification(pdf_text: str, prompt: str) -> str:
    """Queries the local AI model for classification based on the extracted text."""
    print_step("Preparing payload for LLM query.")

    system_prompt = (
        "You are an expert automated document classification system. "
        "You must rigidly follow the instructions and output ONLY the exact category name requested. "
        "Do not provide any explanations, reasoning, or conversational text."
    )

    full_prompt = f"{prompt}\n\n### TEXTO DO DOCUMENTO ###\n{pdf_text}\n\n### SUA RESPOSTA (APENAS A CATEGORIA EXATA) ###\n"

    try:
        print_step("Sending request to the model...")
        response: ChatResponse = client.chat(
            system_prompt=system_prompt,
            input_data=full_prompt,
            temperature=0.0,
        )
        content: Optional[str] = None
        if "output" in response:
            for item in response.get("output", []):
                if item.get("type") == "message":
                    content = item.get("content")
                    break

        if content:
            print_success(f"Model responded: {content.strip()}")
            return content.strip()

        print_error("Model returned an empty response.")
        return ""
    except Exception as e:
        print_error(f"API Error communicating with Local LM Studio: {e}")
        return ""


def normalize_text(text: str) -> str:
    """Normalize text to lowercase, strip accents, and remove punctuation."""
    normalized = unicodedata.normalize('NFD', text)
    normalized = ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')
    normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized.lower())
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def find_target_directory(parent_dir: str, current_dir: str, llm_response: str) -> Optional[str]:
    """Finds the most appropriate target directory based on the LLM response."""
    print_step("Analyzing LLM response to match target folder...")

    if not llm_response:
        print_error("LLM response is empty, cannot match directory.")
        return None

    normalized_response = normalize_text(llm_response)
    normalized_response_words = set(normalized_response.split())

    best_score = 0
    best_match = None
    current_dir_name = os.path.basename(current_dir)

    try:
        for entry in os.listdir(parent_dir):
            if entry == current_dir_name:
                continue

            full_path = os.path.join(parent_dir, entry)
            if not os.path.isdir(full_path):
                continue

            normalized_entry = normalize_text(entry)
            score = 0

            if normalized_entry == normalized_response:
                score += 200

            if normalized_entry in normalized_response:
                score += 100
            if normalized_response in normalized_entry:
                score += 80

            common_words = normalized_response_words.intersection(set(normalized_entry.split()))
            score += len(common_words) * 10

            if score > best_score:
                best_score = score
                best_match = full_path

            if score >= 200:
                print_success(f"Exact/High confidence match found: {full_path}")
                return full_path

    except Exception as e:
        print_error(f"Error reading parent directory: {e}")

    if best_match and best_score > 0:
        print_success(f"Best fuzzy match found: {best_match} (Score: {best_score})")
        return best_match

    print_error("No suitable target directory matched.")
    return None


def move_file_and_related(file_path: str, target_dir: str, current_dir: str) -> bool:
    """Moves the PDF file and any related files sharing the exact same base name."""
    print_step(f"Preparing to move files to: {target_dir}")

    file_name = os.path.basename(file_path)
    target_path = os.path.join(target_dir, file_name)
    base_name, ext = os.path.splitext(file_name)

    # Collision avoidance for main file
    if os.path.exists(target_path):
        counter = 2
        while True:
            new_file_name = f"{base_name} ({counter}){ext}"
            new_target_path = os.path.join(target_dir, new_file_name)
            if not os.path.exists(new_target_path):
                target_path = new_target_path
                break
            counter += 1

    try:
        shutil.move(file_path, target_path)
        print_success(f"Moved main PDF to: {target_path}")

        orig_base_name = os.path.splitext(file_name)[0]
        final_base_name = os.path.splitext(os.path.basename(target_path))[0]

        # Move related files
        files_in_dir = os.listdir(current_dir)
        total = len(files_in_dir)
        success_count = 0
        fail_count = 0

        for idx, related_file in enumerate(files_in_dir):
            if related_file == file_name:
                continue
            
            rel_path = os.path.join(current_dir, related_file)
            if not os.path.isfile(rel_path):
                continue
            
            rel_base, rel_ext = os.path.splitext(related_file)
            if rel_base == orig_base_name:
                print_step(f"Found associated file: '{related_file}'")
                related_target = os.path.join(target_dir, f"{final_base_name}{rel_ext}")
                try:
                    shutil.move(rel_path, related_target)
                    print_success(f"Moved related file to: {related_target}")
                    success_count += 1
                except Exception as e:
                    print_error(f"Error moving related file {related_file}: {e}")
                    fail_count += 1
            
            print_progress(idx + 1, total, prefix='Associated Files Progress', suffix='Complete', length=30)
            
        if success_count > 0 or fail_count > 0:
            print_summary_box("Associated Files Moving", success_count + fail_count, success_count, fail_count)

        return True
    except Exception as e:
        print_error(f"Error moving main file {file_path}: {e}")
        return False


def classify_and_move_pdf(file_path: str, pdf_text: str) -> bool:
    """
    Coordinates the process of classifying the PDF and moving it and its associated files.
    """
    print_step(f"Starting classification process for '{os.path.basename(file_path)}'.")

    current_dir = os.path.dirname(file_path)
    parent_dir = os.path.dirname(current_dir)

    print_step("Calling get_classify_prompt")
    prompt = get_classify_prompt(parent_dir, current_dir)
    if not prompt:
        print_error("Failed to build prompt. Aborting classify process.")
        return False
    
    pdf_text = pdf_text[:4000]

    print_step("Calling query_model_classification")
    llm_response = query_model_classification(pdf_text, prompt)
    if not llm_response:
        print_error("Failed to get classification from model. Aborting classify process.")
        return False

    print_step("Calling find_target_directory")
    target_dir = find_target_directory(parent_dir, current_dir, llm_response)
    if not target_dir:
        print_error("Failed to find target directory. Aborting classify process.")
        return False

    print_step("Calling move_file_and_related")
    success = move_file_and_related(file_path, target_dir, current_dir)

    if success:
        print_success("Primary PDF moved successfully.")
        return True
    else:
        print_error("Primary PDF moving failed.")
        return False


class DropZone(QLabel):
    """A QLabel subclass that accepts PDF file drops."""

    def __init__(self) -> None:
        """Initializes the DropZone widget with styling and drop events enabled."""
        try:
            print_step("Initializing DropZone widget.")
            super().__init__()
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setText("Drag and Drop PDF File Here\n\n🔹 Action: Classify & Move\n(Moves to the best matching category folder)")
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
        print_step(f"=== Beginning processing cycle for dropped file: {file_path} ===")
        success_count = 0
        fail_count = 0
        total = 1

        try:
            print_step("Attempting to extract text from dropped PDF.")
            text = extract_pdf_text(file_path)

            if not text:
                print_error("Failed to extract text or PDF is empty. Processing aborted.")
                fail_count += 1
            else:
                print_success(f"Extracted {len(text)} characters of text.")
                print_step("Proceeding to classify and move the PDF.")

                classify_success = classify_and_move_pdf(file_path, text)
                if classify_success:
                    success_count += 1
                    print_success(f"Completed processing for dropped file: {file_path}")
                else:
                    fail_count += 1
                    print_error(f"Failed to classify and move dropped file: {file_path}")

            print_progress(1, total, prefix='Dropped File Progress', suffix='Complete', length=30)
            print_summary_box("Dropped File Processing Cycle", total, success_count, fail_count)

        except Exception as e:
            print_error(f"Critical error processing dropped file: {e}")
            print_summary_box("Dropped File Processing Cycle (Interrupted)", total, success_count, fail_count)


class MainWindow(QMainWindow):
    """Main application window containing the drop zone."""

    def __init__(self) -> None:
        """Initializes the main window and its layout."""
        try:
            print_step("Initializing MainWindow.")
            super().__init__()
            self.setWindowTitle("PDF Classify Drop")
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

        print_success("Application started successfully. Waiting for PDF drops...")
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
