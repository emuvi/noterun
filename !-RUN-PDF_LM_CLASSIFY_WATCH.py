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




# --- Setup & API Functions ---

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


_cached_prompt = None
_cached_parent_mtime = 0
_failed_to_move_files = set()


def get_classify_prompt(parent_dir: str, current_dir: str) -> str:
    """Generates the prompt instruction dynamically based on parent directory folders."""
    global _cached_prompt, _cached_parent_mtime
    try:
        current_mtime = os.stat(parent_dir).st_mtime
    except OSError:
        current_mtime = 0

    if _cached_prompt is not None and current_mtime == _cached_parent_mtime:
        return _cached_prompt

    func_name = "Generate Prompt"
    print_step(func_name, "Scanning target categories in parent directory...")

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
                func_name, "No category folders found in the parent directory.")
            return ""

        for d in sorted(dirs):
            prompt += f"- {d}\n"

        print_success(
            func_name, f"Found {len(dirs)} category folders to use in prompt.")

    except Exception as e:
        print_error(
            func_name, f"Error reading parent directory to generate prompt: {e}")
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
    func_name = "Extract PDF Text"
    print_step(func_name, f"Opening file '{file_path}'.")
    text = ""
    try:
        with open(file_path, 'rb') as pdf_file:
            reader = PyPDF2.PdfReader(pdf_file)
            total_pages = len(reader.pages)

            print_step(
                func_name, f"Found {total_pages} pages. Calculating extraction ranges...")

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
                func_name, f"Extracting text from {len(pages_to_extract)} selected pages.")
            for page_num in pages_to_extract:
                try:
                    page = reader.pages[page_num]
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
                except Exception as inner_e:
                    print_error(
                        func_name, f"Failed to extract text from page {page_num}: {inner_e}")

        if text.strip():
            print_success(func_name, "Text extraction completed successfully.")
        else:
            print_error(func_name, "Extracted text is empty.")

    except Exception as e:
        print_error(func_name, f"Error reading PDF {file_path}: {e}")

    return text.strip()


def query_model_classification(client: LMStd, pdf_text: str, prompt: str) -> str:
    """Queries the local AI model for classification based on the extracted text."""
    func_name = "Query Classification Model"
    print_step(func_name, "Preparing payload for LLM query.")

    system_prompt = (
        "You are an expert automated document classification system. "
        "You must rigidly follow the instructions and output ONLY the exact category name requested. "
        "Do not provide any explanations, reasoning, or conversational text."
    )

    full_prompt = f"{prompt}\n\n### TEXTO DO DOCUMENTO ###\n{pdf_text}\n\n### SUA RESPOSTA (APENAS A CATEGORIA EXATA) ###\n"

    try:
        print_step(func_name, "Sending request to the model...")
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
            print_success(func_name, f"Model responded: {content.strip()}")
            return content.strip()

        print_error(func_name, "Model returned an empty response.")
        return ""
    except Exception as e:
        print_error(
            func_name, f"API Error communicating with Local LM Studio: {e}")
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
    func_name = "Find Target Directory"
    print_step(func_name, "Analyzing LLM response to match target folder...")

    if not llm_response:
        print_error(func_name, "LLM response is empty, cannot match directory.")
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
                    func_name, f"Exact/High confidence match found: {full_path}")
                return full_path

    except Exception as e:
        print_error(func_name, f"Error reading parent directory: {e}")

    if best_match and best_score > 0:
        print_success(
            func_name, f"Best fuzzy match found: {best_match} (Score: {best_score})")
        return best_match

    print_error(func_name, "No suitable target directory matched.")
    return None


def handle_file_error(file_path: str, current_dir: str, error_log: str) -> None:
    """
    Moves the file to '!-ERRORS' to prevent it from being endlessly processed.
    Also attempts to move related files sharing the same basename.
    """
    func_name = "Move On Error"
    print_step(
        func_name, f"Moving '{file_path}' to '!-ERRORS' to prevent loop...")
    base_name, ext = os.path.splitext(file_path)
    errors_dir = os.path.join(current_dir, "!-ERRORS")
    os.makedirs(errors_dir, exist_ok=True)
    error_path = os.path.join(errors_dir, file_path)

    try:
        shutil.move(os.path.join(current_dir, file_path), error_path)
        print_success(
            func_name, f"Moved main file to '!-ERRORS'")

        # Save the error log
        log_file_path = os.path.join(errors_dir, f"{base_name}.log")
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(event_chain) + "\n\n[FINAL ERROR]\n" + error_log)
        print_success(func_name, f"Saved error log to '{log_file_path}'")

        # Move related files
        for related_file in os.listdir(current_dir):
            if related_file != file_path and os.path.splitext(related_file)[0] == base_name:
                try:
                    shutil.move(os.path.join(current_dir, related_file),
                                os.path.join(errors_dir, related_file))
                    print_success(
                        func_name, f"Moved related file '{related_file}' to '!-ERRORS'")
                except Exception as e:
                    print_error(
                        func_name, f"Failed to move related file {related_file}: {e}")
    except Exception as e:
        print_error(
            func_name, f"Failed to move main file {file_path}: {e}")
        global _failed_to_move_files
        _failed_to_move_files.add(file_path)


def move_associated_files(current_dir: str, target_dir: str, orig_base_name: str, final_base_name: str, orig_pdf_name: str) -> None:
    """
    Searches for and moves other files in the directory that share the same old base name.
    Includes a progress cycle.
    """
    func_name = "Move Associated Files"
    print_step(func_name, f"Searching for associated files with base name '{orig_base_name}' in '{current_dir}'.")
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
                if f_base_name == orig_base_name and f != orig_pdf_name:
                    print_step(func_name, f"Found associated file: '{f}'")
                    new_f_name = f"{final_base_name}{f_ext}"
                    new_f_path = os.path.join(target_dir, new_f_name)

                    print_step(func_name, f"Checking if target path '{new_f_path}' exists.")
                    if os.path.exists(new_f_path):
                        print_error(func_name, f"Cannot move '{f}' to '{new_f_name}' because target already exists.")
                        fail_count += 1
                        continue

                    print_step(func_name, f"Attempting to move associated file '{f}' to '{new_f_name}'.")
                    try:
                        shutil.move(f_path, new_f_path)
                        print_success(func_name, f"Moved associated file '{f}' to '{new_f_name}'")
                        success_count += 1
                    except Exception as move_err:
                        print_error(func_name, f"Failed to move associated file '{f}': {move_err}")
                        fail_count += 1

            except Exception as file_err:
                print_error(func_name, f"Error processing potential associated file '{f}': {file_err}")
                fail_count += 1

        print_success(func_name, "Completed scanning and moving associated files.")
        if success_count > 0 or fail_count > 0:
            print_summary_box("Associated Files Moving", success_count + fail_count, success_count, fail_count)

    except Exception as e:
        print_error(func_name, f"Error during associated files moving process: {e}")


def move_file_and_related(file_path: str, target_dir: str, current_dir: str) -> bool:
    """Moves the PDF file and any related files sharing the exact same base name."""
    func_name = "Move Files and Sidecars"
    print_step(func_name, f"Preparing to move files to: {target_dir}")

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
        print_success(func_name, f"Moved main PDF to: {target_path}")

        orig_base_name = os.path.splitext(file_path)[0]
        final_base_name = os.path.splitext(os.path.basename(target_path))[0]

        # Move related files
        move_associated_files(current_dir, target_dir, orig_base_name, final_base_name, file_path)

        return True
    except Exception as e:
        print_error(func_name, f"Error moving main file {file_path}: {e}")
        return False


# --- Main Execution Loop ---

def main() -> None:
    current_dir = os.getcwd()
    parent_dir = os.path.dirname(current_dir)

    log_message("=== Automated PDF Classifier ===")

    client = init_lmstd_client()
    if not client:
        log_message("Failed to initialize AI Client. Aborting.")
        return

    prompt_text = get_classify_prompt(parent_dir, current_dir)
    if not prompt_text:
        log_message("Could not generate instruction prompt. Aborting.")
        return

    print("\nThis script will continuously monitor the current folder for new PDF files (excluding 'RAND*') to classify and move.")
    print("It will classify files into the subfolders of the parent directory.")
    proceed = input("Do you want to proceed? (yes/no): ").strip().lower()
    if proceed != 'yes':
        log_message("Operation canceled.")
        return

    log_message(
        "Starting continuous classification watcher. Press Ctrl+C to stop.")
    print("-" * 90)

    total_session_success = 0
    total_session_fails = 0
    waiting = False

    try:
        while True:
            try:
                # Refresh prompt text occasionally in case folders changed
                prompt_text = get_classify_prompt(parent_dir, current_dir)

                pdf_files = sorted(glob.glob("*.pdf"))
                files_to_process = []
                for f in pdf_files:
                    if f.upper().startswith("RAND"):
                        continue
                    if f in _failed_to_move_files:
                        continue
                    files_to_process.append(f)

                if not files_to_process:
                    if not waiting:
                        print(
                            f"\r[{get_current_time()}] ⏳ Waiting for new PDF files... (Checking every 5s)", end="", flush=True)
                        waiting = True
                    time.sleep(5)
                    continue

                if waiting:
                    print()  # Move to the next line so we don't overwrite the waiting message
                    waiting = False

                total_files_in_cycle = len(files_to_process)
                cycle_success = 0
                cycle_fails = 0

                log_message(
                    f"=== Starting New Cycle: Found {total_files_in_cycle} file(s) to process ===")

                for index, file in enumerate(files_to_process, 1):
                    event_chain.clear()
                    file_success = 0
                    file_fail = 0
                    percentage = (index / total_files_in_cycle) * 100
                    print(
                        f"\n[{get_current_time()}] --- Processing File {index} of {total_files_in_cycle} ({percentage:.1f}%) ---")
                    log_message(f"Target File: {file}")

                    try:
                        # 1. Extract Text
                        text = extract_pdf_text(file)
                        if not text:
                            error_msg = "Failed to extract text or PDF is empty."
                            handle_file_error(
                                file, current_dir, error_msg)
                            cycle_fails += 1
                            file_fail = 1
                        else:
                            # 2. LLM Classification
                            start_time = time.time()
                            llm_response = query_model_classification(
                                client, text, prompt_text)
                            elapsed_time = time.time() - start_time
                            log_message(
                                f"LLM Processing Time: {elapsed_time:.2f}s")

                            if not llm_response:
                                error_msg = "LLM returned empty or unparseable response."
                                handle_file_error(
                                    file, current_dir, error_msg)
                                cycle_fails += 1
                                file_fail = 1
                                time.sleep(2)
                            else:
                                # 3. Directory Matching
                                target_dir = find_target_directory(
                                    parent_dir, current_dir, llm_response)
                                if target_dir:
                                    # 4. File Moving
                                    success = move_file_and_related(
                                        file, target_dir, current_dir)
                                    if success:
                                        cycle_success += 1
                                        file_success = 1
                                    else:
                                        error_msg = f"Failed to move file '{file}' to target directory '{target_dir}'."
                                        handle_file_error(file, current_dir, error_msg)
                                        cycle_fails += 1
                                        file_fail = 1
                                        time.sleep(2)
                                else:
                                    error_msg = "No suitable target directory found for file."
                                    handle_file_error(
                                        file, current_dir, error_msg)
                                    cycle_fails += 1
                                    file_fail = 1

                    except ConnectionError as ce:
                        print_error(
                            "Cycle Loop", f"API Error: {ce}. Skipping to next file.")
                        cycle_fails += 1
                        file_fail = 1
                        time.sleep(2)
                    except Exception as e:
                        error_msg = f"Unexpected error processing '{file}': {e}\n{traceback.format_exc()}"
                        print_error(
                            "Cycle Loop", error_msg)
                        handle_file_error(file, current_dir, error_msg)
                        cycle_fails += 1
                        file_fail = 1
                        time.sleep(2)
                        
                    print_summary_box("Cycle Summary", 1, file_success, file_fail)
                    print_summary_box("Overall Session Summary", total_session_success + total_session_fails +
                                      cycle_success + cycle_fails, total_session_success + cycle_success, total_session_fails + cycle_fails)

                # End of Cycle
                total_session_success += cycle_success
                total_session_fails += cycle_fails

                print_summary_box(
                    title=f"Overall Session Summary",
                    total=total_session_success + total_session_fails,
                    success=total_session_success,
                    fails=total_session_fails
                )

                time.sleep(2)

            except Exception as e:
                log_message(f"Unexpected error in the main loop: {e}")
                traceback.print_exc()
                time.sleep(5)

    except KeyboardInterrupt:
        print(f"\n[{get_current_time()}] Continuous monitoring stopped by user.")


if __name__ == "__main__":
    main()
