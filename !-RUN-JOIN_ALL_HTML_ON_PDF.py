import asyncio
import logging
import shutil
import sys
import tempfile
import time
import warnings
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
logging.getLogger("pypdf").setLevel(logging.ERROR)

try:
    from playwright.async_api import async_playwright
except ImportError as e:
    print(f"[-] Required library 'playwright' is not installed: {e}. Install with: pip install playwright", file=sys.stderr)
    sys.exit(1)

try:
    from pypdf import PdfWriter
except ImportError as e:
    print(f"[-] Required library 'pypdf' is not installed: {e}. Install with: pip install pypdf", file=sys.stderr)
    sys.exit(1)

# ==============================================================================
# GLOBAL CONFIGURATION
# ==============================================================================
# Determines whether to delete origin files after processing.
# True  -> Deletes the files automatically without asking.
# False -> Keeps the files without asking.
# None  -> Prompts the user to decide.
DELETE_ORIGIN_FILES = None
# ==============================================================================


def print_error(message: str) -> None:
    """Prints an error message to stderr."""
    print(message, file=sys.stderr)


async def html_to_pdfs(html_files, temp_dir):
    pdf_paths = []
    successful_html_files = []
    failed_count = 0

    # Start headless browser
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        total_files = len(html_files)
        for idx, file_path in enumerate(html_files):
            try:
                rel_label = file_path.relative_to(Path.cwd())
            except ValueError:
                rel_label = file_path.name

            try:
                # Convert Windows path to a file:// URI
                abs_path = file_path.absolute().as_posix()
                file_url = f"file:///{abs_path}"

                # Navigate to the local HTML file and wait for it to fully load
                # Use 'load' instead of 'networkidle' because saved pages often have background scripts that hang
                try:
                    await page.goto(file_url, wait_until='load', timeout=20000)
                except Exception:
                    print(f"  [!] Warning: {file_path.name} timed out during load, attempting to render what we have...")

                # Define output PDF path with sequential naming (00000.pdf, 00001.pdf, etc.)
                pdf_path = temp_dir / f"{idx:05d}.pdf"

                # Print page to PDF
                await page.pdf(path=str(pdf_path), format="A3", print_background=False)
                pdf_paths.append(pdf_path)
                successful_html_files.append(file_path)

                print(f"  [{idx + 1}/{total_files}] Converted: {rel_label}")
            except Exception as e:
                failed_count += 1
                print_error(f"  [X] ERROR: Failed to convert {rel_label}. Reason: {e}")
                # Workaround: recreate page if it crashed so remaining files can still convert
                try:
                    if page.is_closed():
                        page = await browser.new_page()
                    else:
                        await page.close()
                        page = await browser.new_page()
                except Exception:
                    try:
                        page = await browser.new_page()
                    except Exception:
                        pass

        try:
            await browser.close()
        except Exception:
            pass
        return pdf_paths, successful_html_files, failed_count


def main() -> int:
    current_folder = Path.cwd()
    temp_folder = current_folder / "temp"
    output_pdf_path = current_folder / "all_html_joined.pdf"
    had_errors = False

    # 1. Search for all .htm and .html files in current and all subdirectories
    print("\n--- STEP 1: SEARCHING FOR HTML FILES ---")
    html_files = []
    try:
        html_files.extend(current_folder.rglob("*.html"))
        html_files.extend(current_folder.rglob("*.htm"))
    except OSError as e:
        print_error(f"[-] Error scanning directory '{current_folder}': {e}")
        return 1

    html_files = sorted(set(html_files))

    if not html_files:
        print("  -> No .htm or .html files found in the current folder or subfolders.")
        return 0

    print(f"  -> Found {len(html_files)} HTML files to process.")

    # 2. Create 'temp' folder (clean it out if it already exists, fallback to unique temp dir if locked)
    try:
        if temp_folder.exists():
            shutil.rmtree(temp_folder)
        temp_folder.mkdir()
    except OSError:
        temp_folder = Path(tempfile.mkdtemp(prefix="temp_html_", dir=str(current_folder)))
        print(f"  [!] Default temp folder busy; using fallback temp folder: {temp_folder.name}")

    # 3. Convert each file to PDF
    print("\n--- STEP 2: CONVERTING HTML TO PDF ---")
    try:
        pdf_files, successful_html_files, failed_count = asyncio.run(html_to_pdfs(html_files, temp_folder))
        if failed_count > 0:
            had_errors = True
    except Exception as e:
        print_error(f"[-] Fatal error launching Chromium/Playwright: {e}")
        shutil.rmtree(temp_folder, ignore_errors=True)
        return 1

    if not pdf_files:
        print_error("[-] No HTML files were successfully converted to PDF. Aborting merge.")
        shutil.rmtree(temp_folder, ignore_errors=True)
        return 1

    # 4. Join all PDFs into a single PDF
    print("\n--- STEP 3: MERGING PDFs ---")
    writer = PdfWriter()
    merged_count = 0

    for pdf_file in sorted(pdf_files):
        try:
            writer.append(str(pdf_file))
            merged_count += 1
        except Exception as e:
            had_errors = True
            print_error(f"[-] Failed to merge '{pdf_file.name}': {e}. Skipping this part.")

    if merged_count == 0:
        print_error("[-] No PDF parts could be merged.")
        shutil.rmtree(temp_folder, ignore_errors=True)
        return 1

    written = False
    last_write_error = None
    for attempt in range(1, 4):
        try:
            with open(output_pdf_path, "wb") as out_file:
                writer.write(out_file)
            written = True
            break
        except OSError as e:
            last_write_error = e
            if attempt < 3:
                time.sleep(0.5 * attempt)

    try:
        writer.close()
    except Exception:
        pass

    if not written:
        print_error(f"[-] Failed to write merged PDF '{output_pdf_path.name}': {last_write_error}")
        shutil.rmtree(temp_folder, ignore_errors=True)
        return 1

    print(f"  -> Success! Merged PDF saved as: {output_pdf_path.name}")

    # 5. Delete the temp folder
    print("\n--- STEP 4: CLEANING UP ---")
    cleaned = False
    for attempt in range(1, 4):
        try:
            shutil.rmtree(temp_folder)
            cleaned = True
            break
        except OSError:
            if attempt < 3:
                time.sleep(0.4 * attempt)
    if not cleaned:
        print_error(f"[-] Could not completely remove temp folder '{temp_folder.name}'.")
        had_errors = True

    print("\n*** ALL DONE! ***")

    if successful_html_files:
        if DELETE_ORIGIN_FILES is True:
            ans = 'y'
        elif DELETE_ORIGIN_FILES is False:
            ans = 'n'
        else:
            try:
                ans = input("\nDo you want to delete the origin files HTML? (Y/N): ")
            except (EOFError, KeyboardInterrupt):
                ans = 'n'

        if ans.strip().lower() == 'y':
            for fp in successful_html_files:
                deleted = False
                last_err = None
                for attempt in range(1, 4):
                    try:
                        fp.unlink()
                        print(f"[+] Origin file deleted: {fp.name}")
                        deleted = True
                        break
                    except Exception as e:
                        last_err = e
                        if attempt < 3:
                            time.sleep(0.4 * attempt)
                if not deleted:
                    had_errors = True
                    print_error(f"[-] Error deleting {fp.name}: {last_err}")

    return 1 if had_errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[*] Process interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print_error(f"[-] Fatal error: {e}")
        sys.exit(1)
