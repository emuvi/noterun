# Copyright (c) 2026 emuvi
# SPDX-License-Identifier: MIT

import runpy
import sys
from pathlib import Path


def print_error(message: str) -> None:
    print(message, file=sys.stderr)


if __name__ == "__main__":
    try:
        script_path = Path(__file__).with_name("!-RUN-MAKE_PDF_OF_HTML.py")
        namespace = runpy.run_path(str(script_path), run_name="make_pdf_of_html")
        sys.exit(namespace["main"](force_overwrite=True))
    except KeyboardInterrupt:
        print("\n[*] Process interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print_error(f"[-] Fatal error: {e}")
        sys.exit(1)
