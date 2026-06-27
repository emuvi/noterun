import os
import sys
import re
import PyPDF2
from datetime import datetime
from typing import Optional, List, Any

from lmstd import LMStd, ChatResponse

# Initialize the LM Studio client pointing to the local LM Studio server.
# Based on renamer.py and pdf_about.py configuration
client = LMStd(base_url=os.environ.get("LMSTD_HOST", "http://localhost:1234"),
               api_token=os.environ.get("LMSTD_APIKEY"))


def get_current_time() -> str:
    """
    Returns the current time formatted as HH:MM:SS.

    Returns:
        str: Formatted current time string.
    """
    try:
        return datetime.now().strftime('%H:%M:%S')
    except Exception as e:
        print(f"[Error] get_current_time failed: {e}")
        return "00:00:00"


def log_message(message: str) -> None:
    """
    Logs a message to the console with a timestamp.

    Args:
        message (str): The message to log.
    """
    try:
        print(f"[{get_current_time()}] {message}")
    except Exception as e:
        print(f"[Error] log_message failed: {e}")


def get_pages_to_extract(total_pages: int) -> List[int]:
    """
    Determines which pages to extract from a PDF based on the total number of pages.
    Extracts up to 99 pages: first 33, middle 33, and last 33 if document is large.

    Args:
        total_pages (int): The total number of pages in the PDF.

    Returns:
        List[int]: A list of page numbers to extract.
    """
    log_message(
        f"Determining pages to extract for a PDF with {total_pages} total pages.")
    pages_to_extract: List[int] = []
    try:
        if total_pages > 99:
            log_message(
                "PDF has more than 99 pages. Selecting first 33, middle 33, and last 33 pages.")
            mid_start = (total_pages // 2) - 16
            pages_to_extract = sorted(set(
                list(range(33)) +
                list(range(mid_start, mid_start + 33)) +
                list(range(total_pages - 33, total_pages))
            ))
        else:
            log_message("PDF has 99 or fewer pages. Selecting all pages.")
            pages_to_extract = list(range(total_pages))
        log_message(
            f"Successfully determined {len(pages_to_extract)} pages to extract.")
    except Exception as e:
        log_message(f"Error determining pages to extract: {e}")
    return pages_to_extract


def extract_text_from_pages(reader: PyPDF2.PdfReader, pages_to_extract: List[int]) -> str:
    """
    Extracts text from specified pages of a PDF reader object.

    Args:
        reader (PyPDF2.PdfReader): The PyPDF2 reader object.
        pages_to_extract (List[int]): The list of page indices to extract text from.

    Returns:
        str: The extracted text.
    """
    log_message(
        f"Extracting text from {len(pages_to_extract)} selected pages.")
    text = ""
    try:
        for page_num in pages_to_extract:
            log_message(f"Extracting text from page {page_num + 1}...")
            try:
                page = reader.pages[page_num]
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
            except Exception as page_err:
                log_message(
                    f"Error extracting text from page {page_num + 1}: {page_err}")
        log_message(
            f"Successfully extracted {len(text)} characters of text from the selected pages.")
    except Exception as e:
        log_message(f"Error during text extraction loop: {e}")
    return text.strip()


def extract_pdf_text(file_path: str) -> str:
    """
    Opens a PDF file and extracts text content from it.

    Args:
        file_path (str): The path to the PDF file.

    Returns:
        str: The extracted text.
    """
    log_message(f"Starting text extraction for PDF file: '{file_path}'")
    text = ""
    try:
        log_message(f"Opening file '{file_path}' in binary read mode.")
        with open(file_path, 'rb') as pdf_file:
            log_message("Initializing PyPDF2 PdfReader.")
            reader = PyPDF2.PdfReader(pdf_file)
            total_pages = len(reader.pages)
            log_message(
                f"PDF reader initialized successfully. Total pages found: {total_pages}.")

            pages_to_extract = get_pages_to_extract(total_pages)
            if not pages_to_extract:
                log_message("No pages to extract. Aborting extraction.")
                return ""

            text = extract_text_from_pages(reader, pages_to_extract)

    except FileNotFoundError:
        log_message(f"Error: File not found at '{file_path}'.")
    except PermissionError:
        log_message(f"Error: Permission denied when accessing '{file_path}'.")
    except Exception as e:
        log_message(f"Error reading PDF '{file_path}': {e}")

    log_message("Text extraction process completed.")
    return text


def build_summary_prompt(text: str) -> str:
    """
    Builds the prompt string for the LLM to generate a summary.

    Args:
        text (str): The extracted PDF text.

    Returns:
        str: The formatted prompt string.
    """
    log_message("Building the prompt for the LLM.")
    prompt = ""
    try:
        truncated_text = text[:4000]
        log_message(
            f"Truncated text to {len(truncated_text)} characters for the prompt.")

        prompt = (
            "Based on the following text extracted from a PDF, tell me what it is about "
            "in a maximum of 100 characters. Be concise and direct, providing only the summary "
            "without conversational filler. Do not use quotes or special characters that "
            "are invalid in filenames. Respond in the exact same language as the provided text, "
            "and ensure perfect spell checking on the language of the document.\n\n"
            f"### TEXT ###\n{truncated_text}"
        )
        log_message("Prompt built successfully.")
    except Exception as e:
        log_message(f"Error building prompt: {e}")
    return prompt


def get_summary_from_llm(prompt: str) -> Optional[str]:
    """
    Calls the Local LM Studio API to get a summary based on the prompt.

    Args:
        prompt (str): The prompt containing instructions and text.

    Returns:
        Optional[str]: The summary string generated by the LLM, or None if an error occurred.
    """
    log_message("Calling the Local LM Studio API for a summary...")
    content: Optional[str] = None
    try:
        log_message("Sending chat request to LM Studio.")
        response: ChatResponse = client.chat(
            system_prompt="You are a helpful assistant that summarizes documents extremely concisely for filenames. Always respond in the same language as the input text and ensure perfect spelling.",
            input_data=prompt,
            temperature=0.0
        )
        log_message("Received response from LM Studio.")

        if "output" in response:
            log_message("Parsing response output.")
            for item in response.get("output", []):
                if item.get("type") == "message":
                    content = item.get("content")
                    log_message(
                        "Successfully extracted message content from response.")
                    break

        if not content:
            log_message("Model returned an empty or invalid response.")
            return None

    except Exception as e:
        log_message(f"Error calling Local LM Studio API: {e}")
        return None

    return content.strip()


def sanitize_filename(summary: str) -> Optional[str]:
    """
    Cleans up the generated summary to be a valid and safe filename.

    Args:
        summary (str): The raw summary text.

    Returns:
        Optional[str]: The sanitized filename base, or None if invalid.
    """
    log_message("Sanitizing the generated summary for use as a filename.")
    try:
        log_message("Removing potential markdown formatting.")
        if summary.startswith("```"):
            summary = summary.split('\n', 1)[-1]
            if summary.endswith("```"):
                summary = summary[:-3]
        summary = summary.strip()

        log_message("Enforcing the 100 character limit.")
        if len(summary) > 100:
            summary = summary[:100].strip()

        log_message("Replacing invalid characters with underscores.")
        new_base_name = re.sub(r'[\\/*?:"<>|\n\r\t]', "_", summary)

        log_message(
            "Removing consecutive underscores and trailing/leading invalid characters.")
        new_base_name = re.sub(r'_{2,}', "_", new_base_name).strip(" _.")

        if not new_base_name:
            log_message(
                "Sanitized summary is empty. Cannot use as a filename.")
            return None

        log_message(f"Successfully sanitized filename base: '{new_base_name}'")
        return new_base_name
    except Exception as e:
        log_message(f"Error sanitizing filename: {e}")
        return None


def get_unique_new_path(current_dir: str, new_base_name: str, original_path: str) -> Optional[str]:
    """
    Generates a unique file path by appending a counter if the file already exists.

    Args:
        current_dir (str): The directory containing the file.
        new_base_name (str): The desired new base name for the file.
        original_path (str): The original path of the file to be renamed.

    Returns:
        Optional[str]: A unique new file path, or None if an error occurred.
    """
    log_message(
        f"Generating a unique new file path for base name '{new_base_name}'.")
    try:
        new_file_name = f"{new_base_name}.pdf"
        new_path = os.path.join(current_dir, new_file_name)

        log_message(f"Checking if path '{new_path}' already exists.")
        if os.path.exists(new_path) and original_path.lower() != new_path.lower():
            log_message(
                "Path already exists. Finding a unique filename with a counter.")
            counter = 2
            while True:
                new_file_name = f"{new_base_name} ({counter}).pdf"
                new_path = os.path.join(current_dir, new_file_name)
                if not os.path.exists(new_path) or original_path.lower() == new_path.lower():
                    log_message(f"Found unique filename: '{new_file_name}'")
                    break
                counter += 1
        else:
            log_message(f"Path '{new_path}' is available.")

        return new_path
    except Exception as e:
        log_message(f"Error generating unique new path: {e}")
        return None


def rename_file(old_path: str, new_path: str) -> bool:
    """
    Renames a file from old_path to new_path.

    Args:
        old_path (str): The current path of the file.
        new_path (str): The destination path of the file.

    Returns:
        bool: True if successful, False otherwise.
    """
    log_message(f"Attempting to rename '{old_path}' to '{new_path}'.")
    try:
        os.rename(old_path, new_path)
        log_message(
            f"Successfully renamed file to '{os.path.basename(new_path)}'.")
        return True
    except FileNotFoundError:
        log_message(
            f"Error: Original file '{old_path}' not found for renaming.")
        return False
    except PermissionError:
        log_message(f"Error: Permission denied when renaming '{old_path}'.")
        return False
    except Exception as e:
        log_message(f"Error renaming file '{old_path}' to '{new_path}': {e}")
        return False


def rename_associated_files(current_dir: str, old_base_name: str, final_new_base_name: str, new_pdf_name: str) -> None:
    """
    Searches for and renames other files in the directory that share the same old base name.

    Args:
        current_dir (str): The directory containing the files.
        old_base_name (str): The original base name of the PDF.
        final_new_base_name (str): The final new base name (including any counters).
        new_pdf_name (str): The full new filename of the PDF to ignore it.
    """
    log_message(
        f"Searching for associated files with base name '{old_base_name}' in '{current_dir}'.")
    try:
        files_in_dir = os.listdir(current_dir)
        log_message(
            f"Found {len(files_in_dir)} files in directory. Filtering associated files.")

        for f in files_in_dir:
            f_path = os.path.join(current_dir, f)
            try:
                if not os.path.isfile(f_path):
                    continue

                f_base_name, f_ext = os.path.splitext(f)

                # Check if this file is an associated file
                if f_base_name == old_base_name and f != new_pdf_name:
                    log_message(f"Found associated file: '{f}'")
                    new_f_name = f"{final_new_base_name}{f_ext}"
                    new_f_path = os.path.join(current_dir, new_f_name)

                    log_message(
                        f"Checking if target path '{new_f_path}' exists.")
                    if os.path.exists(new_f_path):
                        log_message(
                            f"Cannot rename '{f}' to '{new_f_name}' because target already exists.")
                        continue

                    log_message(
                        f"Attempting to rename associated file '{f}' to '{new_f_name}'.")
                    if rename_file(f_path, new_f_path):
                        log_message(
                            f"Also renamed associated file '{f}' to '{new_f_name}'")
                    else:
                        log_message(f"Failed to rename associated file '{f}'.")
            except Exception as file_err:
                log_message(
                    f"Error processing potential associated file '{f}': {file_err}")

    except Exception as e:
        log_message(f"Error during associated files renaming process: {e}")


def rename_pdf_from_summary(file_path: str, pdf_text: str) -> None:
    """
    Coordinates the process of generating a summary and renaming the PDF and its associated files.

    Args:
        file_path (str): The path to the PDF file.
        pdf_text (str): The extracted text from the PDF.
    """
    log_message(
        f"Starting renaming process for '{os.path.basename(file_path)}'.")

    prompt = build_summary_prompt(pdf_text)
    if not prompt:
        log_message("Failed to build prompt. Aborting rename process.")
        return

    summary = get_summary_from_llm(prompt)
    if not summary:
        log_message("Failed to generate summary. Aborting rename process.")
        return

    new_base_name = sanitize_filename(summary)
    if not new_base_name:
        log_message("Failed to sanitize filename. Aborting rename process.")
        return

    current_dir = os.path.dirname(file_path)
    new_path = get_unique_new_path(current_dir, new_base_name, file_path)

    if not new_path:
        log_message(
            "Failed to determine a unique new path. Aborting rename process.")
        return

    old_base_name = os.path.splitext(os.path.basename(file_path))[0]
    new_file_name = os.path.basename(new_path)
    final_new_base_name = os.path.splitext(new_file_name)[0]

    log_message(
        f"Ready to rename from '{old_base_name}.pdf' to '{new_file_name}'.")
    success = rename_file(file_path, new_path)

    if success:
        log_message(
            "Primary PDF renamed successfully. Proceeding to rename associated files.")
        rename_associated_files(
            current_dir, old_base_name, final_new_base_name, new_file_name)
    else:
        log_message(
            "Primary PDF renaming failed. Associated files will not be renamed.")


def process_all_pdfs() -> None:
    """
    Iterates over all PDF files in the current working directory and processes them.
    """
    log_message("Starting batch processing of all PDF files.")
    try:
        current_dir = os.getcwd()
        log_message(f"Current working directory is: {current_dir}")
        log_message(f"Scanning for PDF files in: {current_dir}")

        try:
            files_in_dir = os.listdir(current_dir)
            pdf_files = [f for f in files_in_dir if f.lower().endswith('.pdf')]
        except Exception as ls_err:
            log_message(f"Error listing directory contents: {ls_err}")
            return

        if not pdf_files:
            log_message(
                "No PDF files found in the current directory. Nothing to do.")
            return

        log_message(f"Found {len(pdf_files)} PDF file(s).")

        for filename in pdf_files:
            try:
                file_path = os.path.join(current_dir, filename)
                log_message(f"=== Processing file: {filename} ===")

                text = extract_pdf_text(file_path)

                if not text:
                    log_message(
                        f"Failed to extract text or PDF is empty for: {filename}")
                    log_message("-" * 40)
                    continue

                log_message(
                    f"Successfully extracted {len(text)} characters of text from '{filename}'.")

                rename_pdf_from_summary(file_path, text)

                log_message(f"=== Finished processing file: {filename} ===")
                log_message("-" * 40)
            except Exception as file_err:
                log_message(
                    f"Unexpected error processing file '{filename}': {file_err}")
                log_message("-" * 40)

    except Exception as e:
        log_message(f"Critical error during batch processing: {e}")


def main() -> None:
    """
    Main application entry point.
    """
    log_message("Batch PDF Renamer started.")
    try:
        process_all_pdfs()
    except Exception as e:
        log_message(f"Error in main execution block: {e}")
    log_message("Batch PDF Renamer finished.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_message("Process interrupted by user. Exiting.")
    except Exception as e:
        log_message(f"Fatal error: {e}")
