# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import os
import subprocess
import sys
import tempfile
from pathlib import Path


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
    output_filename = "union_audio_archive.m4a"
    output_file_path = current_dir / output_filename

    print(f"[*] Scanning directory: {current_dir} for audio and video files...")

    files_to_convert = []

    try:
        for file_path in current_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in media_extensions:
                # Skip the output file if it already exists to avoid recursive looping
                if file_path.name == output_filename:
                    continue
                files_to_convert.append(file_path)
    except OSError as e:
        print(f"[-] File System Error while scanning directory: {e}")
        return 1
    except Exception as e:
        print(f"[-] An unexpected error occurred while scanning directory: {e}")
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

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        concat_list_path = temp_dir_path / "concat.txt"
        
        valid_wav_files = []
        
        for idx, file_path in enumerate(files_to_convert, start=1):
            temp_wav_name = f"{idx:05d}.wav"
            temp_wav_path = temp_dir_path / temp_wav_name

            print(f"[*] Preparing ({idx}/{len(files_to_convert)}): '{file_path.name}'...")

            # FFmpeg parameters to convert to intermediate WAV format:
            # -vn : disable video processing (extract audio stream only)
            # -ac 1 : downmix to mono
            # -ar 16000 : lower sample rate to 16kHz
            # -c:a pcm_s16le : standard 16-bit PCM WAV (lossless)
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

            try:
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                valid_wav_files.append(temp_wav_name)
                success_count += 1
            except subprocess.CalledProcessError as e:
                print(f"[-] Error converting '{file_path.name}' to intermediate format: Subprocess failed with exit code {e.returncode}")
                if e.stderr:
                    print(f"    FFmpeg stderr: {e.stderr.strip()}")
                failure_count += 1
            except FileNotFoundError:
                print("[-] CRITICAL ERROR: ffmpeg was not found.")
                print("[-] Please make sure ffmpeg is installed and added to your system's PATH.")
                return 1
            except Exception as e:
                print(f"[-] An unexpected error occurred while converting '{file_path.name}': {e}")
                failure_count += 1

        if not valid_wav_files:
            print("[-] No valid files were successfully processed. Aborting union operation.")
            return 1
            
        print("-" * 50)
        print(f"[*] Uniting {len(valid_wav_files)} processed files into '{output_filename}'...")

        # Create concat.txt containing the list of temporary wav files
        try:
            with open(concat_list_path, 'w', encoding='utf-8') as f:
                for wav_name in valid_wav_files:
                    f.write(f"file '{wav_name}'\n")
        except Exception as e:
            print(f"[-] Error writing concat list: {e}")
            return 1

        # Run ffmpeg concat
        # We explicitly set the codecs again just to be sure we encode to the right format
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
            # Run in the temp directory so it can find the wav files easily
            result = subprocess.run(concat_cmd, cwd=temp_dir_path, check=True, capture_output=True, text=True)
            print(f"[+] Successfully created union archive '{output_filename}'.")
        except subprocess.CalledProcessError as e:
            print(f"[-] Error uniting files: Subprocess failed with exit code {e.returncode}")
            if e.stderr:
                print(f"    FFmpeg stderr: {e.stderr.strip()}")
            return 1
        except Exception as e:
            print(f"[-] An unexpected error occurred while uniting files: {e}")
            return 1

    print("-" * 50)
    print(f"[*] Union process completed.")
    print(f"[+] Files successfully processed: {success_count}")

    if failure_count > 0:
        print(f"[-] Failed to process {failure_count} files (skipped in final archive).")
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code)
