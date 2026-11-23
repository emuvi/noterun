# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import io
import logging
import os
import sys
import time
import warnings

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


def read_input(prompt: str = "") -> str:
    """
    Prints the prompt to stdout and reads a line from stdin without writing to stderr.
    Avoids CPython's interactive input(prompt) writing prompts to stderr on Windows consoles.
    """
    if prompt:
        print(prompt, end="", flush=True)
    line = sys.stdin.readline()
    if line == "":
        raise EOFError
    return line.rstrip("\r\n")


try:
    from pypdf import PdfReader, PdfWriter
except ImportError as e:
    print_error(f"[-] Required library 'pypdf' is not installed: {e}. Install with: pip install pypdf")
    sys.exit(1)

# ==============================================================================
# CONFIGURAÇÕES (Settings)
# ==============================================================================
# Tamanho máximo desejado para cada arquivo PDF gerado (em Megabytes)
MAX_SIZE_MB = 20

# Percentual alvo do tamanho máximo que cada arquivo deve atingir (ex: 0.95 = 95%).
# O script adicionará mais páginas continuamente até chegar nesse percentual.
TARGET_PERCENTAGE = 0.95

# Determines whether to delete origin files after processing.
# True  -> Deletes the files automatically without asking.
# False -> Keeps the files without asking.
# None  -> Prompts the user to decide.
DELETE_ORIGIN_FILES = None
# ==============================================================================

def process_pdf(filepath: str, directory: str, filename: str) -> bool:
    """
    Splits a large PDF into smaller files (under MAX_SIZE_MB).
    Ensures pages are kept in order and files have a numerical suffix.
    """
    MAX_SIZE = MAX_SIZE_MB * 1024 * 1024
    TARGET_SIZE = MAX_SIZE * TARGET_PERCENTAGE

    file_size = os.path.getsize(filepath)
    if file_size < MAX_SIZE:
        return True
        
    print(f"[*] Splitting large PDF: '{filename}' ({file_size/1024/1024:.2f}MB)")
    
    success = False
    generated_files = []
    
    try:
        with open(filepath, "rb") as f_in:
            reader = PdfReader(f_in)
            if getattr(reader, "is_encrypted", False):
                try:
                    reader.decrypt("")
                except Exception:
                    pass
            total_pages = len(reader.pages)
            
            if total_pages == 0:
                print_error(f"[-] '{filename}' has 0 pages. Skipping.")
                return False
                
            if total_pages == 1:
                print_error(f"[-] '{filename}' is a single page over {MAX_SIZE_MB}MB. Cannot split.")
                return False
                
            avg_page_size = file_size / total_pages
            
            part_num = 1
            start_page = 0
            
            while start_page < total_pages:
                lower_bound = start_page + 1
                upper_bound = total_pages + 1
                
                if avg_page_size > 0:
                    guess = max(1, int(TARGET_SIZE / avg_page_size))
                else:
                    guess = 1
                end_page = min(start_page + guess, total_pages)
                
                best_end_page = start_page + 1
                best_writer = None
                best_size = 0
                
                while lower_bound < upper_bound:
                    writer = PdfWriter()
                    for i in range(start_page, end_page):
                        writer.add_page(reader.pages[i])
                        
                    mem_file = io.BytesIO()
                    writer.write(mem_file)
                    size = mem_file.tell()
                    
                    if size >= MAX_SIZE:
                        upper_bound = end_page
                        if end_page == start_page + 1:
                            best_end_page = end_page
                            best_size = size
                            best_writer = writer
                            break
                            
                        new_pages = max(1, int((end_page - start_page) * (TARGET_SIZE / size)))
                        next_end = start_page + new_pages
                        
                        if next_end >= upper_bound:
                            next_end = upper_bound - 1
                        if next_end < lower_bound:
                            next_end = lower_bound
                        end_page = next_end
                    else:
                        best_end_page = end_page
                        best_size = size
                        best_writer = writer
                        
                        lower_bound = end_page + 1
                        
                        if end_page == total_pages:
                            break
                        if size >= TARGET_SIZE:
                            break
                            
                        avg_page_in_chunk = size / (end_page - start_page) if (end_page - start_page) > 0 else avg_page_size
                        if avg_page_in_chunk <= 0:
                            avg_page_in_chunk = 1024
                            
                        bytes_missing = TARGET_SIZE - size
                        extra_pages = max(1, int(bytes_missing / avg_page_in_chunk))
                        
                        next_end = end_page + extra_pages
                        if next_end >= upper_bound:
                            next_end = end_page + max(1, (upper_bound - end_page) // 2)
                            
                        end_page = next_end
                        if end_page < lower_bound:
                            end_page = lower_bound
                
                base_name, ext = os.path.splitext(filename)
                out_filename = f"{base_name} ({part_num:03d}){ext}"
                out_filepath = os.path.join(directory, out_filename)
                dup_counter = 2
                while os.path.exists(out_filepath):
                    out_filename = f"{base_name} ({part_num:03d}) ({dup_counter}){ext}"
                    out_filepath = os.path.join(directory, out_filename)
                    dup_counter += 1
                
                if best_writer is None:
                    raise RuntimeError(f"Could not determine a valid split for {filename} at page {start_page}")
                
                with open(out_filepath, "wb") as f_out:
                    best_writer.write(f_out)
                    
                actual_size = os.path.getsize(out_filepath)
                generated_files.append((out_filepath, best_end_page - start_page))
                print(f"    -> Created '{out_filename}' ({actual_size/1024/1024:.2f}MB, pages {start_page+1}-{best_end_page})")
                
                avg_page_size = actual_size / (best_end_page - start_page)
                
                start_page = best_end_page
                part_num += 1
                
            total_pages_written = sum(count for _, count in generated_files)
            
            if total_pages_written == total_pages:
                success = True
            else:
                print_error(f"[-] Page count mismatch: expected {total_pages}, got {total_pages_written}")
                success = False

    except Exception as e:
        print_error(f"[-] Unexpected error splitting '{filename}': {e}")
        # Clean up any partial files if there was an error
        for fp, _ in generated_files:
            if os.path.exists(fp):
                try:
                    os.remove(fp)
                except OSError:
                    pass
        return False
        
    if success:
        print(f"[+] Successfully split '{filename}'. Original file preserved.\n")
        return True
            
    return False

def filter_eligible_pdfs(directory: str) -> tuple:
    """
    Scans the directory for PDF files that might need splitting.
    """
    print(f"[*] Scanning directory '{directory}' for PDF files...")
    eligible_files = []
    
    try:
        entries = os.listdir(directory)
    except PermissionError as e:
        print_error(f"[-] Permission Denied accessing directory '{directory}': {e}")
        return [], False
    except Exception as e:
        print_error(f"[-] Unexpected error accessing directory '{directory}': {e}")
        return [], False

    for filename in entries:
        filepath = os.path.join(directory, filename)
        
        try:
            if os.path.isfile(filepath) and filename.lower().endswith('.pdf'):
                if filename.startswith('!-') or filename.startswith('_'):
                    continue
                eligible_files.append((directory, filename))
        except OSError:
            continue
            
    print(f"[+] Found {len(eligible_files)} PDF file(s) for evaluation.\n")
    return eligible_files, True

def main():
    print("=" * 50)
    print("   Noterun Split Large PDFs Script Initialized")
    print("=" * 50)
    
    script_dir = os.getcwd()
    files_to_process, scan_ok = filter_eligible_pdfs(script_dir)
    if not scan_ok:
        return 1
    
    if not files_to_process:
        print("[*] No PDF files to process. Exiting.")
        return 0
        
    print("-" * 50)
    
    success_count = 0
    failure_count = 0
    skipped_count = 0
    processed_files = []
    
    for dirpath, filename in files_to_process:
        filepath = os.path.join(dirpath, filename)
        try:
            file_size = os.path.getsize(filepath)
        except OSError as e:
            print_error(f"[-] Could not retrieve size for '{filename}': {e}")
            failure_count += 1
            continue
        
        if file_size < MAX_SIZE_MB * 1024 * 1024:
            skipped_count += 1
            continue
            
        if process_pdf(filepath, dirpath, filename):
            success_count += 1
            processed_files.append(filepath)
        else:
            failure_count += 1
            
    print("-" * 50)
    print(f"[*] Process completed.")
    print(f"[+] Successfully split: {success_count}")
    print(f"[*] Skipped (already under {MAX_SIZE_MB}MB): {skipped_count}")
    
    if failure_count > 0:
        print_error(f"[-] Errors encountered: {failure_count}")
    else:
        print("[+] Process finished without errors!")

    if processed_files:
        if DELETE_ORIGIN_FILES is True:
            ans = 'y'
        elif DELETE_ORIGIN_FILES is False:
            ans = 'n'
        else:
            try:
                ans = read_input("\nDo you want to delete the origin files? (Y/N): ")
            except (EOFError, KeyboardInterrupt):
                ans = 'n'
            
        if ans.strip().lower() == 'y':
            for fp in processed_files:
                deleted = False
                last_err = None
                for attempt in range(1, 4):
                    try:
                        os.remove(fp)
                        print(f"[+] Origin file deleted: {os.path.basename(fp)}")
                        deleted = True
                        break
                    except Exception as e:
                        last_err = e
                        if attempt < 3:
                            time.sleep(0.4 * attempt)
                if not deleted:
                    failure_count += 1
                    print_error(f"[-] Error deleting {os.path.basename(fp)}: {last_err}")

    return 1 if failure_count > 0 else 0

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
