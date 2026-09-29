import re
from datetime import datetime
from pathlib import Path


OUTPUT_FILENAME = "!-LIST_ALL_DEMANDS.txt"
FILENAME_PATTERN = re.compile(
    r"^(\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}) - (\d+) - (.+)\.pdf$",
    re.IGNORECASE,
)


def parse_demand_filename(filename):
    """Extract the timestamp, demand number, and title from a matching PDF name."""
    match = FILENAME_PATTERN.match(filename)
    if not match:
        return None

    timestamp, number, title = match.groups()
    try:
        parsed_timestamp = datetime.strptime(timestamp, "%Y.%m.%d-%H.%M")
    except ValueError:
        return None

    title = title.strip()
    if not title:
        return None

    return parsed_timestamp, timestamp, number, title


def collect_latest_demands(directory):
    """Return the latest matching PDF record for each demand number."""
    latest_by_number = {}

    for filepath in directory.iterdir():
        if not filepath.is_file() or filepath.suffix.lower() != ".pdf":
            continue

        record = parse_demand_filename(filepath.name)
        if record is None:
            continue

        parsed_timestamp, _, number, _ = record
        current = latest_by_number.get(number)
        if current is None or parsed_timestamp >= current[0]:
            latest_by_number[number] = record

    return sorted(latest_by_number.values(), key=lambda record: (record[0], record[2]), reverse=True)


def write_report(directory, demands):
    """Write the selected demand rows to the text report."""
    report_path = directory / OUTPUT_FILENAME
    report_lines = [
        f"{timestamp} - {number} - {title}"
        for _, timestamp, number, title in demands
    ]
    report_path.write_text("\n".join(report_lines) + ("\n" if report_lines else ""), encoding="utf-8")
    return report_path


def main():
    directory = Path.cwd()
    print(f"[*] Scanning '{directory}' for matching PDF files...")

    try:
        demands = collect_latest_demands(directory)
        report_path = write_report(directory, demands)
    except OSError as error:
        print(f"[-] Failed to generate the demand list: {error}")
        return 1

    print(f"[+] Wrote {len(demands)} unique demands to '{report_path.name}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())