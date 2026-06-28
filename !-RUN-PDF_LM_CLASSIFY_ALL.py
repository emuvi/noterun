import os
import re
import glob
import time
import shutil
import unicodedata
import traceback
import PyPDF2
import sys
from typing import Optional, List, Tuple
from datetime import datetime
from lmstd import LMStd, ChatResponse

# --- Visualization and Logging Helpers ---

def get_current_time() -> str:
    """Returns the current time formatted as HH:MM:SS."""
    return datetime.now().strftime('%H:%M:%S')

def log_message(message: str) -> None:
    """Logs a general message to the console with a timestamp."""
    print(f"[{get_current_time()}] {message}")

def print_step(message: str) -> None:
    """Prints a step being executed with a visual indicator."""
    print(f"[{get_current_time()}] 🔹 [STEP] {message}")

def print_success(message: str) -> None:
    """Prints a success message with a visual indicator."""
    print(f"[{get_current_time()}] ✅ [SUCCESS] {message}")

def print_error(message: str) -> None:
    """Prints an error message with a visual indicator."""
    print(f"[{get_current_time()}] 🔴 [ERROR] {message}")

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

def print_summary_box(title: str, total: int, successes: int, fails: int) -> None:
    """Prints a visual box containing the summary of a cycle or session."""
    box_width = 50
    print("\n" + "╔" + "═" * (box_width - 2) + "╗")
    title_str = f" 📊 SUMMARY: {title} "
    print("║" + title_str.center(box_width - 2) + "║")
    print("╠" + "═" * (box_width - 2) + "╣")
    print("║" + f" Total Items Processed : {total:<21}".ljust(box_width - 2) + "║")
    print("║" + f" ✅ Successes          : {successes:<21}".ljust(box_width - 2) + "║")
    print("║" + f" 🔴 Failures           : {fails:<21}".ljust(box_width - 2) + "║")
    print("╚" + "═" * (box_width - 2) + "╝\n")

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
        print_success("Init LMStd Client: LMStd client initialized successfully.")
        return client
    except Exception as e:
        print_error(f"Init LMStd Client: Failed to initialize LMStd client: {e}")
        return None


def get_classify_prompt(parent_dir: str, current_dir: str) -> str:
    """Generates the prompt instruction dynamically based on parent directory folders."""
    print_step("Generate Prompt: Scanning target categories in parent directory...")

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
            print_error("Generate Prompt: No category folders found in the parent directory.")
            return ""

        for d in sorted(dirs):
            prompt += f"- {d}\n"

        print_success(f"Generate Prompt: Found {len(dirs)} category folders to use in prompt.")

    except Exception as e:
        print_error(f"Generate Prompt: Error reading parent directory to generate prompt: {e}")
        return ""

    prompt += (
        "\n### INSTRUÇÕES CRÍTICAS ###\n"
        "1. Analise o tema principal e o conteúdo do documento com cuidado.\n"
        "2. Escolha a categoria da lista acima que melhor descreve o documento.\n"
        "3. Sua resposta DEVE SER APENAS O NOME EXATO DA CATEGORIA. Não inclua absolutamente mais nada.\n"
        "4. NÃO forneça justificativas, NÃO escreva frases como 'A categoria é', e NÃO coloque pontos finais após o nome.\n"
    )
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

            print_step(f"Extract PDF Text: Found {total_pages} pages. Calculating extraction ranges...")

            if total_pages > 99:
                mid_start = (total_pages // 2) - 16
                pages_to_extract = sorted(set(
                    list(range(33)) +
                    list(range(mid_start, mid_start + 33)) +
                    list(range(total_pages - 33, total_pages))
                ))
            else:
                pages_to_extract = list(range(total_pages))

            print_step(f"Extract PDF Text: Extracting text from {len(pages_to_extract)} selected pages.")
            for page_num in pages_to_extract:
                try:
                    page = reader.pages[page_num]
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
                except Exception as inner_e:
                    print_error(f"Extract PDF Text: Failed to extract text from page {page_num}: {inner_e}")

        if text.strip():
            print_success("Extract PDF Text: Text extraction completed successfully.")
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
            print_success(f"Query Classification Model: Model responded: {content.strip()}")
            return content.strip()

        print_error("Query Classification Model: Model returned an empty response.")
        return ""
    except Exception as e:
        print_error(f"Query Classification Model: API Error communicating with Local LM Studio: {e}")
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
    print_step("Find Target Directory: Analyzing LLM response to match target folder...")

    if not llm_response:
        print_error("Find Target Directory: LLM response is empty, cannot match directory.")
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
                print_success(f"Find Target Directory: Exact/High confidence match found: {full_path}")
                return full_path

    except Exception as e:
        print_error(f"Find Target Directory: Error reading parent directory: {e}")

    if best_match and best_score > 0:
        print_success(f"Find Target Directory: Best fuzzy match found: {best_match} (Score: {best_score})")
        return best_match

    print_error("Find Target Directory: No suitable target directory matched.")
    return None


def rename_file_on_error(file_path: str, suffix: str, current_dir: str) -> None:
    """
    Renames the file to prevent it from being endlessly processed.
    Also attempts to rename related files sharing the same basename.
    """
    print_step(f"Rename On Error: Applying '{suffix}' suffix to file to prevent loop...")
    base_name, ext = os.path.splitext(file_path)
    error_name = f"{base_name} {suffix}{ext}"

    try:
        os.rename(os.path.join(current_dir, file_path), os.path.join(current_dir, error_name))
        print_success(f"Rename On Error: Renamed main file to: {error_name}")

        # Rename related files
        for related_file in os.listdir(current_dir):
            if related_file != file_path and os.path.splitext(related_file)[0] == base_name:
                rel_ext = os.path.splitext(related_file)[1]
                related_error_name = f"{base_name} {suffix}{rel_ext}"
                try:
                    os.rename(os.path.join(current_dir, related_file), os.path.join(current_dir, related_error_name))
                    print_success(f"Rename On Error: Renamed related file to: {related_error_name}")
                except Exception as e:
                    print_error(f"Rename On Error: Failed to rename related file {related_file}: {e}")
    except Exception as e:
        print_error(f"Rename On Error: Failed to rename main file {file_path}: {e}")


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
        for related_file in os.listdir(current_dir):
            if related_file == file_path:
                continue
            rel_base, rel_ext = os.path.splitext(related_file)
            if rel_base == orig_base_name:
                related_target = os.path.join(
                    target_dir, f"{final_base_name}{rel_ext}")
                try:
                    shutil.move(os.path.join(
                        current_dir, related_file), related_target)
                    print_success(f"Move Files: Moved related file to: {related_target}")
                except Exception as e:
                    print_error(f"Move Files: Error moving related file {related_file}: {e}")

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
            if "(UNREADABLE)" in f or "(UNCLASSIFIED)" in f or "(ERROR)" in f:
                continue
            files_to_process.append(f)

        total = len(files_to_process)

        if total == 0:
            print_error("No PDF files found in the current directory. Nothing to do.")
            return

        print_success(f"Found {total} PDF file(s).")

        for idx, file in enumerate(files_to_process):
            print_step(f"=== Beginning processing cycle for file: {file} ({idx+1}/{total}) ===")
            try:
                # 1. Extract Text
                text = extract_pdf_text(os.path.join(current_dir, file))
                if not text:
                    rename_file_on_error(file, "(UNREADABLE)", current_dir)
                    fail_count += 1
                else:
                    text = text[:4000]

                    # 2. LLM Classification
                    start_time = time.time()
                    llm_response = query_model_classification(client, text, prompt_text)
                    elapsed_time = time.time() - start_time
                    log_message(f"LLM Processing Time: {elapsed_time:.2f}s")

                    if not llm_response:
                        rename_file_on_error(file, "(UNCLASSIFIED)", current_dir)
                        fail_count += 1
                    else:
                        # 3. Directory Matching
                        target_dir = find_target_directory(parent_dir, current_dir, llm_response)
                        if target_dir:
                            # 4. File Moving
                            success = move_file_and_related(file, target_dir, current_dir)
                            if success:
                                success_count += 1
                                print_success(f"Fully processed {file}")
                            else:
                                fail_count += 1
                                print_error(f"Failed to fully process {file}")
                        else:
                            rename_file_on_error(file, "(UNCLASSIFIED)", current_dir)
                            fail_count += 1

            except ConnectionError as ce:
                print_error(f"API Error: {ce}. Skipping to next file.")
                fail_count += 1
            except Exception as e:
                print_error(f"Unexpected error processing '{file}': {e}")
                traceback.print_exc()
                rename_file_on_error(file, "(ERROR)", current_dir)
                fail_count += 1

            print_progress(idx + 1, total, prefix='Batch Processing Progress', suffix='Complete', length=30)

        print_success("Batch processing cycle complete.")
        print_summary_box("Batch PDF Classification Cycle", total, success_count, fail_count)

    except Exception as e:
        print_error(f"Critical error during batch processing: {e}")
        print_summary_box("Batch PDF Classification Cycle (Interrupted)", total, success_count, fail_count)


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
