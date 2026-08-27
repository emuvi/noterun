# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import subprocess
import sys
from pathlib import Path


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
        '.mp3', '.wav', '.flac', '.ogg', '.aac', '.wma', '.opus', '.m4b', '.aiff', '.alac'
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
                # Skip already archived files to avoid duplicate conversions
                if file_path.name.endswith(' (arch).m4a'):
                    continue
                # Avoid attempting to convert a file onto itself if source is already .m4a
                if file_path.suffix.lower() == '.m4a':
                    continue
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

    print(f"[+] Found {len(files_to_convert)} media file(s) to convert.")
    print("-" * 50)

    success_count = 0
    failure_count = 0

    for file_path in files_to_convert:
        output_file = file_path.with_name(f"{file_path.stem}.m4a")

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
        except subprocess.CalledProcessError as e:
            print(
                f"[-] Error converting '{file_path.name}': Subprocess failed with exit code {e.returncode}")
            if e.stderr:
                print(f"    FFmpeg stderr: {e.stderr.strip()}")
            failure_count += 1
        except FileNotFoundError:
            print("[-] CRITICAL ERROR: ffmpeg was not found.")
            print(
                "[-] Please make sure ffmpeg is installed and added to your system's PATH.")
            return 1
        except Exception as e:
            print(
                f"[-] An unexpected error occurred while converting '{file_path.name}': {e}")
            failure_count += 1

    print("-" * 50)
    print(f"[*] Conversion process completed.")
    print(f"[+] Successful conversions: {success_count}")

    if failure_count > 0:
        print(f"[-] Failed conversions: {failure_count}")
        return 1
    else:
        print("[+] All media files converted successfully!")
        return 0


if __name__ == "__main__":
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code)
