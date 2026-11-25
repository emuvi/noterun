# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import asyncio
import logging
import sys
import time
import warnings
from pathlib import Path
from typing import List, Optional, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
logging.getLogger("playwright").setLevel(logging.ERROR)

try:
    from playwright.async_api import async_playwright
except ImportError as e:
    print(
        f"[-] Required library 'playwright' is not installed: {e}. "
        "Install with: pip install playwright",
        file=sys.stderr,
    )
    sys.exit(1)

# True deletes converted HTML files automatically.
# False keeps them. None prompts after conversion.
DELETE_ORIGIN_FILES = None


def print_error(message: str) -> None:
    print(message, file=sys.stderr)


def read_input(prompt: str = "") -> str:
    if prompt:
        print(prompt, end="", flush=True)
    line = sys.stdin.readline()
    if line == "":
        raise EOFError
    return line.rstrip("\r\n")


def get_safe_output_path(base_path: Path, reserved_paths: Optional[Set[Path]] = None) -> Path:
    if not base_path.exists() and (
        reserved_paths is None or base_path not in reserved_paths
    ):
        return base_path

    counter = 2
    while True:
        candidate = base_path.with_name(
            f"{base_path.stem} ({counter}){base_path.suffix}"
        )
        if not candidate.exists() and (
            reserved_paths is None or candidate not in reserved_paths
        ):
            return candidate
        counter += 1


def find_html_files(current_dir: Path) -> Optional[List[Path]]:
    files_to_convert = []
    try:
        for file_path in current_dir.iterdir():
            try:
                if file_path.is_file() and file_path.suffix.lower() in {".htm", ".html"}:
                    files_to_convert.append(file_path)
            except OSError:
                continue
    except OSError as e:
        print_error(f"[-] File System Error while scanning directory: {e}")
        return None
    except Exception as e:
        print_error(f"[-] Unexpected error while scanning directory: {e}")
        return None

    return sorted(files_to_convert, key=lambda path: path.name.lower())


async def html_to_pdfs(
    files_to_convert: List[Tuple[Path, Path]],
) -> Tuple[int, List[Path]]:
    success_count = 0
    failure_count = 0
    processed_files = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            for file_path, output_path in files_to_convert:
                print(f"[*] Converting: '{file_path.name}' -> '{output_path.name}'...")
                try:
                    await page.goto(
                        file_path.resolve().as_uri(),
                        wait_until="load",
                        timeout=20000,
                    )
                    await page.pdf(
                        path=str(output_path),
                        format="A3",
                        print_background=False,
                    )
                    print(f"[+] Successfully created '{output_path.name}'.")
                    success_count += 1
                    processed_files.append(file_path)
                except Exception as e:
                    print_error(
                        f"[-] Error converting '{file_path.name}': {e}"
                    )
                    failure_count += 1
                    if page.is_closed():
                        try:
                            page = await browser.new_page()
                        except Exception as page_error:
                            remaining = len(files_to_convert) - len(processed_files) - failure_count
                            print_error(
                                f"[-] Could not create a new browser page: {page_error}"
                            )
                            failure_count += remaining
                            break
        finally:
            await browser.close()

    return failure_count, processed_files


def delete_origin_files(processed_files: List[Path]) -> int:
    if not processed_files:
        return 0

    if DELETE_ORIGIN_FILES is True:
        answer = "y"
    elif DELETE_ORIGIN_FILES is False:
        answer = "n"
    else:
        try:
            answer = read_input("\nDo you want to delete the origin files? (Y/N): ")
        except (EOFError, KeyboardInterrupt):
            answer = "n"

    if answer.strip().lower() != "y":
        return 0

    failure_count = 0
    for file_path in processed_files:
        deleted = False
        last_error = None
        for attempt in range(1, 4):
            try:
                if file_path.exists():
                    file_path.unlink()
                    print(f"[+] Origin file deleted: {file_path.name}")
                deleted = True
                break
            except Exception as e:
                last_error = e
                if attempt < 3:
                    time.sleep(0.4 * attempt)
        if not deleted:
            failure_count += 1
            print_error(f"[-] Error deleting '{file_path.name}': {last_error}")

    return failure_count


def main(force_overwrite: bool = False) -> int:
    print("=" * 50)
    print("   Noterun HTML to PDF Converter Initialized")
    print("=" * 50)

    current_dir = Path.cwd()
    print(f"[*] Scanning directory: {current_dir} for HTML files...")
    html_files = find_html_files(current_dir)
    if html_files is None:
        return 1
    if not html_files:
        print("[*] No HTML files to convert. Exiting.")
        return 0

    print(f"[+] Found {len(html_files)} HTML file(s) to convert.")
    print("-" * 50)

    files_to_convert = []
    failure_count = 0
    reserved_output_paths = set()

    if force_overwrite:
        output_groups = {}
        for file_path in html_files:
            output_path = file_path.with_suffix(".pdf")
            output_groups.setdefault(output_path, []).append(file_path)

        for output_path, source_files in output_groups.items():
            if len(source_files) > 1:
                failure_count += len(source_files)
                names = ", ".join(file_path.name for file_path in source_files)
                print_error(
                    f"[-] Multiple HTML files map to '{output_path.name}'; "
                    f"skipping to avoid overwriting: {names}"
                )
            else:
                files_to_convert.append((source_files[0], output_path))
    else:
        for file_path in html_files:
            base_output = file_path.with_suffix(".pdf")
            output_path = get_safe_output_path(
                base_output, reserved_output_paths
            )
            reserved_output_paths.add(output_path)
            files_to_convert.append((file_path, output_path))

    if not files_to_convert:
        print_error("[-] No HTML files could be converted.")
        return 1

    print("-" * 50)
    try:
        conversion_failures, processed_files = asyncio.run(
            html_to_pdfs(files_to_convert)
        )
        failure_count += conversion_failures
    except Exception as e:
        print_error(f"[-] Fatal error launching Chromium/Playwright: {e}")
        return 1

    print("-" * 50)
    print("[*] Conversion process completed.")
    print(f"[+] Successful conversions: {len(processed_files)}")
    if failure_count:
        print_error(f"[-] Failed conversions: {failure_count}")
    else:
        print("[+] All HTML files converted successfully!")

    failure_count += delete_origin_files(processed_files)
    return 1 if failure_count else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[*] Process interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print_error(f"[-] Fatal error: {e}")
        sys.exit(1)
