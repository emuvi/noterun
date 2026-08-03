# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import sys
import io

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    import subprocess
    print("[*] 'pypdf' library not found. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pypdf"])
    from pypdf import PdfReader, PdfWriter

# ==============================================================================
# CONFIGURAÇÕES (Settings)
# ==============================================================================
# Tamanho máximo desejado para cada arquivo PDF gerado (em Megabytes)
MAX_SIZE_MB = 20

# Percentual alvo do tamanho máximo que cada arquivo deve atingir (ex: 0.95 = 95%).
# O script adicionará mais páginas continuamente até chegar nesse percentual.
TARGET_PERCENTAGE = 0.95
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
            total_pages = len(reader.pages)
            
            if total_pages == 0:
                print(f"[-] '{filename}' has 0 pages. Skipping.")
                return False
                
            if total_pages == 1:
                print(f"[-] '{filename}' is a single page over {MAX_SIZE_MB}MB. Cannot split.")
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
                print(f"[-] Page count mismatch: expected {total_pages}, got {total_pages_written}")
                success = False

    except Exception as e:
        print(f"[-] Unexpected error splitting '{filename}': {e}")
        # Clean up any partial files if there was an error
        for fp, _ in generated_files:
            if os.path.exists(fp):
                try:
                    os.remove(fp)
                except:
                    pass
        return False
        
    if success:
        try:
            os.remove(filepath)
            print(f"[+] Successfully split and deleted original file '{filename}'.\n")
            return True
        except Exception as e:
            print(f"[-] Successfully split, but failed to delete original file '{filename}': {e}\n")
            return False
            
    return False

def filter_eligible_pdfs(directory: str) -> list:
    """
    Scans the directory for PDF files that might need splitting.
    """
    print(f"[*] Scanning directory '{directory}' for PDF files...")
    eligible_files = []
    
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        
        if os.path.isfile(filepath) and filename.lower().endswith('.pdf'):
            if filename.startswith('!-') or filename.startswith('_'):
                continue
            eligible_files.append((directory, filename))
            
    print(f"[+] Found {len(eligible_files)} PDF file(s) for evaluation.\n")
    return eligible_files

def main():
    print("=" * 50)
    print("   Noterun Split Large PDFs Script Initialized")
    print("=" * 50)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    files_to_process = filter_eligible_pdfs(script_dir)
    
    if not files_to_process:
        print("[*] No PDF files to process. Exiting.")
        return 0
        
    print("-" * 50)
    
    success_count = 0
    failure_count = 0
    skipped_count = 0
    
    for dirpath, filename in files_to_process:
        filepath = os.path.join(dirpath, filename)
        file_size = os.path.getsize(filepath)
        
        if file_size < MAX_SIZE_MB * 1024 * 1024:
            skipped_count += 1
            continue
            
        if process_pdf(filepath, dirpath, filename):
            success_count += 1
        else:
            failure_count += 1
            
    print("-" * 50)
    print(f"[*] Process completed.")
    print(f"[+] Successfully split: {success_count}")
    print(f"[*] Skipped (already under {MAX_SIZE_MB}MB): {skipped_count}")
    
    if failure_count > 0:
        print(f"[-] Errors encountered: {failure_count}")
        return 1
    else:
        print("[+] Process finished without errors!")
        return 0

if __name__ == '__main__':
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code)
