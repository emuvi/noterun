# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import subprocess
import sys
from pathlib import Path

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
    and video files to highly compressed, mono .m4a files optimized for voice archiving.
    """
    print("=" * 50)
    print("   Noterun Audio Archive Converter Initialized")
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

    print(f"[*] Scanning directory: {current_dir} for audio and video files...")

    files_to_convert = []

    try:
        for file_path in current_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in media_extensions:
                files_to_convert.append(file_path)
    except OSError as e:
        print(f"[-] File System Error while scanning directory: {e}")
        return 1
    except Exception as e:
        print(
            f"[-] An unexpected error occurred while scanning directory: {e}")
        return 1

    if not files_to_convert:
        print("[*] No audio or video files to convert. Exiting.")
        return 0

    # Sort files alphabetically to ensure consistent processing order
    files_to_convert.sort(key=lambda x: x.name)

    print(f"[+] Found {len(files_to_convert)} media file(s) to convert.")
    print("-" * 50)

    success_count = 0
    failure_count = 0
    processed_files = []
    reserved_output_paths = set()

    for file_path in files_to_convert:
        base_output = file_path.with_name(f"{file_path.stem}.m4a")
        output_file = get_safe_output_path(base_output, reserved_output_paths)
        reserved_output_paths.add(output_file)

        print(f"[*] Converting: '{file_path.name}' -> '{output_file.name}'...")

        # FFmpeg parameters for extreme voice compression:
        # -vn : disable video processing (extract audio stream only)
        # -c:a aac : use native AAC encoder (since it's widely supported for m4a)
        # -ac 1 : downmix to mono
        # -ar 16000 : lower sample rate to 16kHz (plenty for voice clarity)
        # -b:a 16k : highly compressed 16 kbps bitrate
        # -y : overwrite output file if it exists
        cmd = [
            'ffmpeg',
            '-i', str(file_path),
            '-vn',
            '-c:a', 'aac',
            '-ac', '1',
            '-ar', '16000',
            '-b:a', '16k',
            '-y',
            str(output_file)
        ]

        try:
            # Capture output to avoid flooding the console, but keep it for errors
            result = subprocess.run(
                cmd, check=True, capture_output=True, text=True)
            print(f"[+] Successfully converted '{output_file.name}'.")
            success_count += 1
            processed_files.append(file_path)
        except subprocess.CalledProcessError as e:
            print(
                f"[-] Error converting '{file_path.name}': Subprocess failed with exit code {e.returncode}")
            if e.stderr:
                print(f"    FFmpeg stderr: {e.stderr.strip()}")
            if output_file.exists():
                try:
                    output_file.unlink()
                except OSError:
                    pass
            failure_count += 1
        except FileNotFoundError:
            print("[-] CRITICAL ERROR: ffmpeg was not found.")
            print(
                "[-] Please make sure ffmpeg is installed and added to your system's PATH.")
            return 1
        except Exception as e:
            print(
                f"[-] An unexpected error occurred while converting '{file_path.name}': {e}")
            if output_file.exists():
                try:
                    output_file.unlink()
                except OSError:
                    pass
            failure_count += 1

    print("-" * 50)
    print(f"[*] Conversion process completed.")
    print(f"[+] Successful conversions: {success_count}")

    if failure_count > 0:
        print(f"[-] Failed conversions: {failure_count}")
    else:
        print("[+] All media files converted successfully!")

    if processed_files:
        if DELETE_ORIGIN_FILES is True:
            ans = 'y'
        elif DELETE_ORIGIN_FILES is False:
            ans = 'n'
        else:
            ans = input("\nDo you want to delete the origin files? (Y/N): ")
            
        if ans.strip().lower() == 'y':
            for fp in processed_files:
                try:
                    if fp.exists():
                        fp.unlink()
                        print(f"[+] Arquivo de origem excluído: {fp.name}")
                except Exception as e:
                    print(f"[-] Erro ao excluir {fp.name}: {e}")

    return 1 if failure_count > 0 else 0


if __name__ == "__main__":
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code)
