# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


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

# ==============================================================================
# GLOBAL CONFIGURATION
# ==============================================================================
# Determines whether to delete origin files after processing.
# True  -> Deletes the files automatically without asking.
# False -> Keeps the files without asking.
# None  -> Prompts the user to decide.
DELETE_ORIGIN_FILES = None
# ==============================================================================


def get_safe_output_path(base_path: Path, reserved_paths: set = None) -> Path:
    """
    Generates a safe target path to avoid overwriting existing files.
    Appends a numerical suffix starting at (2), e.g., 'stem (2).ext', 'stem (3).ext',
    if a file with the target name already exists (or is in reserved_paths).

    Args:
        base_path (Path): The original desired output path.
        reserved_paths (set, optional): Set of paths already reserved in the current run.

    Returns:
        Path: A safe, unique file path.
    """
    if not base_path.exists() and (reserved_paths is None or base_path not in reserved_paths):
        return base_path

    parent = base_path.parent
    stem = base_path.stem
    ext = base_path.suffix

    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){ext}"
        if not candidate.exists() and (reserved_paths is None or candidate not in reserved_paths):
            return candidate
        counter += 1


def main():
    """
    Main execution function. Orchestrates the scanning and conversion of audio
    and video files, uniting them into a single highly compressed, mono .m4a file.
    """
    print("=" * 50)
    print("   Noterun Union Audio Archive Converter Initialized")
    print("=" * 50)

    # Common audio and video file extensions to convert
    audio_extensions = {
        '.mp3', '.wav', '.flac', '.ogg', '.aac', '.wma', '.opus', '.m4b', '.aiff', '.alac', '.m4a'
    }
    video_extensions = {
        '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.3g2', '.mpg', '.mpeg', '.ts', '.m2ts', '.ogv', '.vob'
    }
    media_extensions = audio_extensions | video_extensions

    current_dir = Path.cwd()
    base_output_path = current_dir / "union_audio_archive.m4a"
    output_file_path = get_safe_output_path(base_output_path)
    output_filename = output_file_path.name

    print(f"[*] Scanning directory: {current_dir} for audio and video files...")

    files_to_convert = []

    try:
        for file_path in current_dir.iterdir():
            try:
                if file_path.is_file() and file_path.suffix.lower() in media_extensions:
                    if file_path.resolve() == output_file_path.resolve():
                        continue
                    files_to_convert.append(file_path)
            except OSError:
                continue
    except OSError as e:
        print_error(f"[-] File System Error while scanning directory: {e}")
        return 1
    except Exception as e:
        print_error(f"[-] An unexpected error occurred while scanning directory: {e}")
        return 1

    if not files_to_convert:
        print("[*] No audio or video files to unite. Exiting.")
        return 0

    # Sort files alphabetically to ensure consistent ordering in the union
    files_to_convert.sort(key=lambda x: x.name)

    print(f"[+] Found {len(files_to_convert)} media file(s) to unite.")
    print("-" * 50)

    success_count = 0
    failure_count = 0
    valid_source_files = []

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        concat_list_path = temp_dir_path / "concat.txt"
        
        valid_wav_files = []
        
        for idx, file_path in enumerate(files_to_convert, start=1):
            temp_wav_name = f"{idx:05d}.wav"
            temp_wav_path = temp_dir_path / temp_wav_name

            print(f"[*] Preparing ({idx}/{len(files_to_convert)}): '{file_path.name}'...")

            cmd = [
                'ffmpeg',
                '-i', str(file_path),
                '-vn',
                '-ac', '1',
                '-ar', '16000',
                '-c:a', 'pcm_s16le',
                '-y',
                str(temp_wav_path)
            ]
            fallback_cmd = [
                'ffmpeg',
                '-err_detect', 'ignore_err',
                '-fflags', '+genpts',
                '-i', str(file_path),
                '-vn',
                '-ac', '1',
                '-ar', '16000',
                '-c:a', 'pcm_s16le',
                '-y',
                str(temp_wav_path)
            ]

            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
                valid_wav_files.append(temp_wav_name)
                valid_source_files.append(file_path)
                success_count += 1
            except FileNotFoundError:
                print_error("[-] CRITICAL ERROR: ffmpeg was not found.")
                print_error("[-] Please make sure ffmpeg is installed and added to your system's PATH.")
                return 1
            except subprocess.CalledProcessError as e:
                print(f"[*] Initial preparation failed for '{file_path.name}'. Retrying with error-tolerant flags...")
                try:
                    subprocess.run(fallback_cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
                    valid_wav_files.append(temp_wav_name)
                    valid_source_files.append(file_path)
                    success_count += 1
                    continue
                except subprocess.CalledProcessError as e2:
                    err_to_show = e2.stderr.strip() if e2.stderr else (e.stderr.strip() if e.stderr else str(e2))
                    print_error(f"[-] Error converting '{file_path.name}' to intermediate format: Subprocess failed with exit code {e2.returncode}")
                    if err_to_show:
                        print_error(f"    FFmpeg stderr: {err_to_show}")
                except Exception as e2:
                    print_error(f"[-] Fallback conversion error for '{file_path.name}': {e2}")
                failure_count += 1
            except Exception as e:
                print_error(f"[-] An unexpected error occurred while converting '{file_path.name}': {e}")
                failure_count += 1

        if not valid_wav_files:
            print_error("[-] No valid files were successfully processed. Aborting union operation.")
            return 1
            
        print("-" * 50)
        print(f"[*] Uniting {len(valid_wav_files)} processed files into '{output_filename}'...")

        try:
            with open(concat_list_path, 'w', encoding='utf-8') as f:
                for wav_name in valid_wav_files:
                    f.write(f"file '{wav_name}'\n")
        except Exception as e:
            print_error(f"[-] Error writing concat list: {e}")
            return 1

        concat_cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', 'concat.txt',
            '-c:a', 'aac',
            '-ac', '1',
            '-ar', '16000',
            '-b:a', '16k',
            '-y',
            str(output_file_path)
        ]

        try:
            subprocess.run(concat_cmd, cwd=temp_dir_path, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            print(f"[+] Successfully created union archive '{output_filename}'.")
        except subprocess.CalledProcessError as e:
            print_error(f"[-] Error uniting files: Subprocess failed with exit code {e.returncode}")
            if e.stderr:
                print_error(f"    FFmpeg stderr: {e.stderr.strip()}")
            if output_file_path.exists():
                try:
                    output_file_path.unlink()
                except OSError:
                    pass
            return 1
        except Exception as e:
            print_error(f"[-] An unexpected error occurred while uniting files: {e}")
            if output_file_path.exists():
                try:
                    output_file_path.unlink()
                except OSError:
                    pass
            return 1

    print("-" * 50)
    print(f"[*] Union process completed.")
    print(f"[+] Files successfully processed: {success_count}")

    if failure_count > 0:
        print_error(f"[-] Failed to process {failure_count} files (skipped in final archive).")
    
    if valid_source_files:
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
            for fp in valid_source_files:
                deleted = False
                last_err = None
                for attempt in range(1, 4):
                    try:
                        if fp.exists():
                            fp.unlink()
                            print(f"[+] Arquivo de origem excluído: {fp.name}")
                        deleted = True
                        break
                    except Exception as e:
                        last_err = e
                        if attempt < 3:
                            time.sleep(0.4 * attempt)
                if not deleted:
                    failure_count += 1
                    print_error(f"[-] Erro ao excluir {fp.name}: {last_err}")

    return 1 if failure_count > 0 else 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[*] Process interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print_error(f"[-] Fatal error: {e}")
        sys.exit(1)
