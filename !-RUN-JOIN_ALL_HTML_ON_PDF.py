import shutil
from pathlib import Path
import asyncio
from playwright.async_api import async_playwright
from PyPDF2 import PdfMerger


async def html_to_pdfs(html_files, temp_dir):
    pdf_paths = []

    # Start headless browser
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        total_files = len(html_files)
        for idx, file_path in enumerate(html_files):
            try:
                # Convert Windows path to a file:// URI
                abs_path = file_path.absolute().as_posix()
                file_url = f"file:///{abs_path}"
    
                # Navigate to the local HTML file and wait for it to fully load
                # Use 'load' instead of 'networkidle' because saved pages often have background scripts that hang
                try:
                    await page.goto(file_url, wait_until='load', timeout=20000)
                except Exception as e:
                    print(f"  [!] Warning: {file_path.name} timed out during load, attempting to render what we have...")
    
                # Define output PDF path with sequential naming (00000.pdf, 00001.pdf, etc.)
                pdf_path = temp_dir / f"{idx:05d}.pdf"
    
                # Print page to PDF (print_background=True ensures CSS backgrounds/images show up)
                await page.pdf(path=str(pdf_path), format="A3", print_background=False)
                pdf_paths.append(pdf_path)
    
                print(f"  [{idx + 1}/{total_files}] Converted: {file_path.relative_to(Path.cwd())}")
            except Exception as e:
                print(f"  [X] ERROR: Failed to convert {file_path.relative_to(Path.cwd())}. Reason: {e}")

        await browser.close()
        return pdf_paths


def main():
    current_folder = Path.cwd()
    temp_folder = current_folder / "temp"
    output_pdf_path = current_folder / "all_html_joined.pdf"

    # 1. Search for all .htm and .html files in current and all subdirectories
    print("\n--- STEP 1: SEARCHING FOR HTML FILES ---")
    html_files = []
    html_files.extend(current_folder.rglob("*.html"))
    html_files.extend(current_folder.rglob("*.htm"))

    if not html_files:
        print("  -> No .htm or .html files found in the current folder or subfolders.")
        return

    print(f"  -> Found {len(html_files)} HTML files to process.")

    # 2. Create 'temp' folder (clean it out if it already exists from a previous run)
    if temp_folder.exists():
        shutil.rmtree(temp_folder)
    temp_folder.mkdir()

    # 3. Convert each file to PDF
    print("\n--- STEP 2: CONVERTING HTML TO PDF ---")
    pdf_files = asyncio.run(html_to_pdfs(html_files, temp_folder))

    # 4. Join all PDFs into a single PDF
    print("\n--- STEP 3: MERGING PDFs ---")
    merger = PdfMerger()

    # Sort the files just to be absolutely sure they merge in sequential order
    for pdf_file in sorted(pdf_files):
        merger.append(str(pdf_file))

    # Write out the final combined PDF
    with open(output_pdf_path, "wb") as out_file:
        merger.write(out_file)
    merger.close()

    print(f"  -> Success! Merged PDF saved as: {output_pdf_path.name}")

    # 5. Delete the temp folder
    print("\n--- STEP 4: CLEANING UP ---")
    shutil.rmtree(temp_folder)
    
    print("\n*** SUCCESS! ALL DONE! ***")


if __name__ == "__main__":
    main()
    print("\nPress Enter to exit...")
    input()
