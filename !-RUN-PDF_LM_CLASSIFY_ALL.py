import glob
import os
import re
import shutil
import time
import traceback
import unicodedata
from datetime import datetime
from typing import List, Optional, Tuple

import PyPDF2
from lmstd import ChatResponse, LMStd

# Global event chain to track execution trace for each file
event_chain: List[str] = []

# --- Visualization and Logging Helpers ---


def get_current_time() -> str:
    """Returns the current time formatted as HH:MM:SS."""
    return datetime.now().strftime('%H:%M:%S')


def log_message(message: str) -> None:
    """Logs a general message to the console with a timestamp."""
    msg = f"[{get_current_time()}] {message}"
    print(msg)
    event_chain.append(msg)


def print_step(message: str) -> None:
    """Prints a step being executed with a visual indicator."""
    msg = f"[{get_current_time()}] 🔹 [STEP] {message}"
    print(msg)
    event_chain.append(msg)


def print_success(message: str) -> None:
    """Prints a success message with a visual indicator."""
    msg = f"[{get_current_time()}] ✅ [SUCCESS] {message}"
    print(msg)
    event_chain.append(msg)


def print_error(message: str) -> None:
    """Prints an error message with a visual indicator."""
    msg = f"[{get_current_time()}] 🔴 [ERROR] {message}"
    print(msg)
    event_chain.append(msg)


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
        print_error(f"Failed to print summary box: {e}")



# --- Setup & API Functions ---


def init_lmstd_client() -> Optional[LMStd]:
    """
    Initializes and returns the LM Studio client.
    Handles any initialization errors.
    """
    print_step("Init LMStd Client: Starting initialization...")
    try:
        client = LMStd(
            base_url=os.environ.get("LMSTD_HOST", "http://localhost:1234"),
            api_token=os.environ.get("LMSTD_APIKEY")
        )
        print_success(
            "Init LMStd Client: LMStd client initialized successfully.")
        return client
    except Exception as e:
        print_error(
            f"Init LMStd Client: Failed to initialize LMStd client: {e}")
        return None


_cached_prompt = None
_cached_parent_mtime = 0


def get_classify_prompt(parent_dir: str, current_dir: str) -> str:
    """Generates the prompt instruction dynamically based on parent directory folders."""
    global _cached_prompt, _cached_parent_mtime
    try:
        current_mtime = os.stat(parent_dir).st_mtime
    except OSError:
        current_mtime = 0

    if _cached_prompt is not None and current_mtime == _cached_parent_mtime:
        return _cached_prompt

    print_step(
        "Generate Prompt: Scanning target categories in parent directory...")

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
            print_error(
                "Generate Prompt: No category folders found in the parent directory.")
            return ""

        for d in sorted(dirs):
            prompt += f"- {d}\n"

        print_success(
            f"Generate Prompt: Found {len(dirs)} category folders to use in prompt.")

    except Exception as e:
        print_error(
            f"Generate Prompt: Error reading parent directory to generate prompt: {e}")
        return ""

    prompt += (
        "\n### INSTRUÇÕES CRÍTICAS ###\n"
        "1. Analise o tema principal e o conteúdo do documento com cuidado.\n"
        "2. Escolha a categoria da lista acima que melhor descreve o documento.\n"
        "3. Sua resposta DEVE SER APENAS O NOME EXATO DA CATEGORIA. Não inclua absolutamente mais nada.\n"
        "4. NÃO forneça justificativas, NÃO escreva frases como 'A categoria é', e NÃO coloque pontos finais após o nome.\n"
    )
    _cached_prompt = prompt
    _cached_parent_mtime = current_mtime
    return prompt


# --- PDF Processing Functions ---

def extract_pdf_text(file_path: str) -> str:
    """
    Extracts text content from a PDF file using PyPDF2.
    Handles extraction logic for large files gracefully.
    """
    print_step(f"Extract PDF Text: Opening file '{file_path}'.")
    text = ""
    try:
        with open(file_path, 'rb') as pdf_file:
            reader = PyPDF2.PdfReader(pdf_file)
            total_pages = len(reader.pages)

            print_step(
                f"Extract PDF Text: Found {total_pages} pages. Calculating extraction ranges...")

            if total_pages > 33:
                mid_start = (total_pages // 2) - 5
                pages_to_extract = sorted(set(
                    list(range(11)) +
                    list(range(mid_start, mid_start + 11)) +
                    list(range(total_pages - 11, total_pages))
                ))
            else:
                pages_to_extract = list(range(total_pages))

            print_step(
                f"Extract PDF Text: Extracting text from {len(pages_to_extract)} selected pages.")
            for page_num in pages_to_extract:
                try:
                    page = reader.pages[page_num]
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
                except Exception as inner_e:
                    print_error(
                        f"Extract PDF Text: Failed to extract text from page {page_num}: {inner_e}")

        if text.strip():
            print_success(
                "Extract PDF Text: Text extraction completed successfully.")
        else:
            print_error("Extract PDF Text: Extracted text is empty.")

    except Exception as e:
        print_error(f"Extract PDF Text: Error reading PDF {file_path}: {e}")

    return text.strip()


def query_model_classification(client: LMStd, pdf_text: str, prompt: str) -> str:
    """Queries the local AI model for classification based on the extracted text."""
    print_step("Query Classification Model: Preparing payload for LLM query.")

    system_prompt = (
        "You are an expert automated document classification system. "
        "You must rigidly follow the instructions and output ONLY the exact category name requested. "
        "Do not provide any explanations, reasoning, or conversational text."
    )

    full_prompt = f"{prompt}\n\n### TEXTO DO DOCUMENTO ###\n{pdf_text}\n\n### SUA RESPOSTA (APENAS A CATEGORIA EXATA) ###\n"

    try:
        print_step("Query Classification Model: Sending request to the model...")
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
            print_success(
                f"Query Classification Model: Model responded: {content.strip()}")
            return content.strip()

        print_error(
            "Query Classification Model: Model returned an empty response.")
        return ""
    except Exception as e:
        print_error(
            f"Query Classification Model: API Error communicating with Local LM Studio: {e}")
        raise ConnectionError(f"API Error: {e}")


# --- Matching and File Management Functions ---

def normalize_text(text: str) -> str:
    """Normalize text to lowercase, strip accents, and remove punctuation."""
    normalized = unicodedata.normalize('NFD', text)
    normalized = ''.join(
        ch for ch in normalized if unicodedata.category(ch) != 'Mn')
    normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized.lower())
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def find_target_directory(parent_dir: str, current_dir: str, llm_response: str) -> Optional[str]:
    """Finds the most appropriate target directory based on the LLM response."""
    print_step(
        "Find Target Directory: Analyzing LLM response to match target folder...")

    if not llm_response:
        print_error(
            "Find Target Directory: LLM response is empty, cannot match directory.")
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

            common_words = normalized_response_words.intersection(
                set(normalized_entry.split()))
            score += len(common_words) * 10

            if score > best_score:
                best_score = score
                best_match = full_path

            if score >= 200:
                print_success(
                    f"Find Target Directory: Exact/High confidence match found: {full_path}")
                return full_path

    except Exception as e:
        print_error(
            f"Find Target Directory: Error reading parent directory: {e}")

    if best_match and best_score > 0:
        print_success(
            f"Find Target Directory: Best fuzzy match found: {best_match} (Score: {best_score})")
        return best_match

    print_error("Find Target Directory: No suitable target directory matched.")
    return None


def handle_file_error(file_path: str, current_dir: str, error_log: str) -> None:
    """
    Moves the file to '!-ERRORS' to prevent it from being endlessly processed.
    Also attempts to move related files sharing the same basename.
    Saves a detailed log file of the error.
    """
    func_name = "Move On Error"
    print_step(
        f"{func_name}: Moving '{file_path}' to '!-ERRORS' to prevent loop...")
    base_name, ext = os.path.splitext(file_path)
    errors_dir = os.path.join(current_dir, "!-ERRORS")
    os.makedirs(errors_dir, exist_ok=True)
    error_path = os.path.join(errors_dir, file_path)

    try:
        shutil.move(os.path.join(current_dir, file_path), error_path)
        print_success(f"{func_name}: Moved main file to '!-ERRORS'")

        # Save the error log
        log_file_path = os.path.join(errors_dir, f"{base_name}.log")
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(event_chain) + "\n\n[FINAL ERROR]\n" + error_log)
        print_success(f"{func_name}: Saved error log to '{log_file_path}'")

        # Move related files
        for related_file in os.listdir(current_dir):
            if related_file != file_path and os.path.splitext(related_file)[0] == base_name:
                try:
                    shutil.move(os.path.join(current_dir, related_file),
                                os.path.join(errors_dir, related_file))
                    print_success(
                        f"{func_name}: Moved related file '{related_file}' to '!-ERRORS'")
                except Exception as e:
                    print_error(
                        f"{func_name}: Failed to move related file {related_file}: {e}")
    except Exception as e:
        print_error(f"{func_name}: Failed to move main file {file_path}: {e}")


def move_associated_files(current_dir: str, target_dir: str, orig_base_name: str, final_base_name: str, orig_pdf_name: str) -> None:
    """
    Searches for and moves other files in the directory that share the same old base name.
    Includes a progress cycle.
    """
    print_step(
        f"Searching for associated files with base name '{orig_base_name}' in '{current_dir}'.")
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
                if f_base_name == orig_base_name and f != orig_pdf_name:
                    print_step(f"Found associated file: '{f}'")
                    new_f_name = f"{final_base_name}{f_ext}"
                    new_f_path = os.path.join(target_dir, new_f_name)

                    print_step(
                        f"Checking if target path '{new_f_path}' exists.")
                    if os.path.exists(new_f_path):
                        print_error(
                            f"Cannot move '{f}' to '{new_f_name}' because target already exists.")
                        fail_count += 1
                        continue

                    print_step(
                        f"Attempting to move associated file '{f}' to '{new_f_name}'.")
                    try:
                        shutil.move(f_path, new_f_path)
                        print_success(
                            f"Moved associated file '{f}' to '{new_f_name}'")
                        success_count += 1
                    except Exception as move_err:
                        print_error(f"Failed to move associated file '{f}': {move_err}")
                        fail_count += 1

            except Exception as file_err:
                print_error(
                    f"Error processing potential associated file '{f}': {file_err}")
                fail_count += 1

        print_success("Completed scanning and moving associated files.")
        if success_count > 0 or fail_count > 0:
            print_summary_box("Associated Files Moving",
                              success_count + fail_count, success_count, fail_count)

    except Exception as e:
        print_error(f"Error during associated files moving process: {e}")


def move_file_and_related(file_path: str, target_dir: str, current_dir: str) -> bool:
    """Moves the PDF file and any related files sharing the exact same base name."""
    print_step(f"Move Files: Preparing to move files to: {target_dir}")

    target_path = os.path.join(target_dir, file_path)
    base_name, ext = os.path.splitext(file_path)

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
        shutil.move(os.path.join(current_dir, file_path), target_path)
        print_success(f"Move Files: Moved main PDF to: {target_path}")

        orig_base_name = os.path.splitext(file_path)[0]
        final_base_name = os.path.splitext(os.path.basename(target_path))[0]

        # Move related files
        move_associated_files(current_dir, target_dir, orig_base_name, final_base_name, file_path)

        return True
    except Exception as e:
        print_error(f"Move Files: Error moving main file {file_path}: {e}")
        return False


def process_all_pdfs() -> None:
    """
    Iterates over all PDF files in the current working directory and processes them once.
    """
    print_step("Starting batch processing of all PDF files.")
    current_dir = os.getcwd()
    parent_dir = os.path.dirname(current_dir)

    client = init_lmstd_client()
    if not client:
        print_error("Failed to initialize AI Client. Aborting.")
        return

    prompt_text = get_classify_prompt(parent_dir, current_dir)
    if not prompt_text:
        print_error("Could not generate instruction prompt. Aborting.")
        return

    success_count = 0
    fail_count = 0
    total = 0

    try:
        print_step(f"Scanning for PDF files in: {current_dir}")
        pdf_files = sorted(glob.glob("*.pdf"))
        files_to_process = []
        for f in pdf_files:
            if f.upper().startswith("RAND"):
                continue
            files_to_process.append(f)

        total = len(files_to_process)

        if total == 0:
            print_error(
                "No PDF files found in the current directory. Nothing to do.")
            return

        print_success(f"Found {total} PDF file(s).")

        for index, file in enumerate(files_to_process):
            event_chain.clear()
            print_step(
                f"=== Beginning processing cycle for file: {file} ({index+1}/{total}) ===")
            try:
                # 1. Extract Text
                text = extract_pdf_text(os.path.join(current_dir, file))
                if not text:
                    error_msg = "Failed to extract text or PDF is empty."
                    handle_file_error(file, current_dir, error_msg)
                    fail_count += 1
                else:
                    # 2. LLM Classification
                    start_time = time.time()
                    llm_response = query_model_classification(
                        client, text, prompt_text)
                    elapsed_time = time.time() - start_time
                    log_message(f"LLM Processing Time: {elapsed_time:.2f}s")

                    if not llm_response:
                        error_msg = "LLM returned empty or unparseable response."
                        handle_file_error(file, current_dir, error_msg)
                        fail_count += 1
                    else:
                        # 3. Directory Matching
                        target_dir = find_target_directory(
                            parent_dir, current_dir, llm_response)
                        if target_dir:
                            # 4. File Moving
                            success = move_file_and_related(
                                file, target_dir, current_dir)
                            if success:
                                success_count += 1
                                print_success(f"Fully processed {file}")
                            else:
                                fail_count += 1
                                print_error(f"Failed to fully process {file}")
                                print_summary_box(
                                    "Cycle Summary", total, success_count, fail_count)
                                print_summary_box(
                                    "Overall Session Summary", total, success_count, fail_count)
                        else:
                            error_msg = "No suitable target directory found for file."
                            handle_file_error(file, current_dir, error_msg)
                            fail_count += 1

            except ConnectionError as ce:
                print_error(f"API Error: {ce}. Skipping to next file.")
                fail_count += 1
            except Exception as e:
                error_msg = f"Unexpected error processing '{file}': {e}\n{traceback.format_exc()}"
                print_error(error_msg)
                handle_file_error(file, current_dir, error_msg)
                fail_count += 1

            print_progress(
                index + 1, total, prefix='Batch Processing Progress', suffix='Complete', length=30)

        print_success("Batch processing cycle complete.")
        print_summary_box("Cycle Summary", total, success_count, fail_count)
        print_summary_box("Overall Session Summary",
                          total, success_count, fail_count)

    except Exception as e:
        print_error(f"Critical error during batch processing: {e}")
        print_summary_box("Cycle Summary (Interrupted)",
                          total, success_count, fail_count)
        print_summary_box("Overall Session Summary (Interrupted)",
                          total, success_count, fail_count)


def main() -> None:
    """
    Main application entry point.
    """
    print_step("Batch PDF Classifier started.")
    try:
        process_all_pdfs()
    except Exception as e:
        print_error(f"Error in main execution block: {e}")
    print_success("Batch PDF Classifier finished.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_error("Process interrupted by user. Exiting.")
    except Exception as e:
        print_error(f"Fatal error: {e}")
