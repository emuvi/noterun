import os
import random
import string
import sys
import time

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


def get_random_name(length=18):
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for i in range(length))


def rename_files_in_directory():
    current_dir = os.getcwd()
    failures = 0

    try:
        entries = os.listdir(current_dir)
    except OSError as e:
        print(f"[-] Error listing directory '{current_dir}': {e}", file=sys.stderr)
        return 1

    for filename in entries:
        file_path = os.path.join(current_dir, filename)

        try:
            if not os.path.isfile(file_path):
                continue
        except OSError:
            continue

        if filename.startswith("!-"):
            continue
        file_extension = os.path.splitext(filename)[1].lower()
        if file_extension != '.pdf':
            continue

        renamed = False
        last_error = None
        for attempt in range(1, 4):
            new_name = "RAND " + get_random_name() + file_extension
            new_file_path = os.path.join(current_dir, new_name)
            while os.path.exists(new_file_path):
                new_name = "RAND " + get_random_name() + file_extension
                new_file_path = os.path.join(current_dir, new_name)

            try:
                os.rename(file_path, new_file_path)
                print(f'Renamed: {filename} -> {new_name}')
                renamed = True
                break
            except OSError as e:
                last_error = e
                if attempt < 3:
                    time.sleep(0.4 * attempt)
            except Exception as e:
                last_error = e
                break

        if not renamed:
            failures += 1
            print(f"[-] Failed to rename '{filename}': {last_error}", file=sys.stderr)

    return 1 if failures > 0 else 0


def main():
    try:
        proceed = read_input(
            "Do you want to proceed with random renaming all files in the current directory? (yes/no): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nOperation canceled.")
        return 0

    if proceed == 'yes':
        exit_code = rename_files_in_directory()
        print("Renaming completed.")
        return exit_code
    else:
        print("Operation canceled.")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nOperation canceled.")
        sys.exit(0)
    except Exception as e:
        print(f"[-] Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
