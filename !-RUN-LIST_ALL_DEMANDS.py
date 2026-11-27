import re
import sys
import time
from datetime import datetime
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



OUTPUT_FILENAME = "!-LIST_ALL_DEMANDS.txt"
FILENAME_PATTERN = re.compile(
    r"^(\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}(?:\.\d{2})?) - (\d+) - (.+)\.pdf$",
    re.IGNORECASE,
)


def parse_demand_filename(filename):
    """Extract the timestamp, demand number, and title from a matching PDF name."""
    match = FILENAME_PATTERN.match(filename)
    if not match:
        return None

    timestamp, number, title = match.groups()
    parsed_timestamp = None
    for fmt in ("%Y.%m.%d-%H.%M.%S", "%Y.%m.%d-%H.%M"):
        try:
            parsed_timestamp = datetime.strptime(timestamp, fmt)
            break
        except ValueError:
            continue
    if parsed_timestamp is None:
        return None

    title = title.strip()
    if not title:
        return None

    return parsed_timestamp, timestamp, number, title


def collect_latest_demands(directory):
    """Return the latest matching PDF record for each demand number."""
    latest_by_number = {}

    for filepath in directory.iterdir():
        try:
            if not filepath.is_file() or filepath.suffix.lower() != ".pdf":
                continue

            record = parse_demand_filename(filepath.name)
            if record is None:
                continue

            parsed_timestamp, _, number, _ = record
            current = latest_by_number.get(number)
            if current is None or parsed_timestamp >= current[0]:
                latest_by_number[number] = record
        except OSError as error:
            print(f"[-] Skipping unreadable entry '{filepath}': {error}", file=sys.stderr)
            continue

    return sorted(latest_by_number.values(), key=lambda record: f"{record[2]}{record[1]}", reverse=True)


def write_report(directory, demands):
    """Write the selected demand rows to the text report."""
    report_path = directory / OUTPUT_FILENAME
    report_lines = [
        f"{timestamp} - {number} - {title}"
        for _, timestamp, number, title in demands
    ]
    content = "\n".join(report_lines) + ("\n" if report_lines else "")
    last_error = None
    for attempt in range(1, 4):
        try:
            report_path.write_text(content, encoding="utf-8")
            return report_path
        except OSError as error:
            last_error = error
            if attempt < 3:
                time.sleep(0.4 * attempt)
    raise last_error


def main():
    directory = Path.cwd()
    print(f"[*] Scanning '{directory}' for matching PDF files...")

    try:
        demands = collect_latest_demands(directory)
        report_path = write_report(directory, demands)
    except OSError as error:
        print(f"[-] Failed to generate the demand list: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"[-] Unexpected error generating the demand list: {error}", file=sys.stderr)
        return 1

    print(f"[+] Wrote {len(demands)} unique demands to '{report_path.name}'.")
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[*] Process interrupted by user.")
        sys.exit(0)
    except Exception as error:
        print(f"[-] Fatal error: {error}", file=sys.stderr)
        sys.exit(1)