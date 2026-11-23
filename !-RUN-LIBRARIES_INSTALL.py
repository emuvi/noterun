import subprocess
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def print_error(message: str) -> None:
    """Prints an error message to stderr."""
    print(message, file=sys.stderr)


def _run_cmd(cmd: list, label: str) -> tuple:
    """Runs a subprocess command capturing stderr so non-error tool notices do not pollute stderr."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        if result.returncode == 0:
            return True, ""
        err_detail = (result.stderr or result.stdout or f"Exit code {result.returncode}").strip()
        return False, err_detail
    except Exception as e:
        return False, str(e)


def install_packages() -> int:
    """Install required Python packages and spacy models from the internet."""
    packages = [
        "pip-system-certs",
        "PyQt5",
        "pypdf",
        "lmstd",
        "click",
        "spacy",
        "pyperclip",
        "langdetect",
        "playwright",
        "Pillow",
        "pandas",
        "fpdf2",
        "openpyxl",
        "xlrd",
        "odfpy",
        "cryptography",
        "pywin32"
    ]

    spacy_models = [
        "de_core_news_sm",
        "el_core_news_sm",
        "en_core_web_sm",
        "es_core_news_sm",
        "fr_core_news_sm",
        "it_core_news_sm",
        "nl_core_news_sm",
        "pt_core_news_sm",
        "ru_core_news_sm",
        "xx_ent_wiki_sm"
    ]

    failed_items = []

    print("Starting the installation of required libraries...")
    print("-" * 50)

    # Update pip first (non-critical workaround if it fails)
    print("Updating pip...")
    ok, _ = _run_cmd([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], "pip")
    if not ok:
        print("Warning: Could not update pip, continuing with installation...")

    # Install packages (resilient: continue installing remaining packages even if one fails)
    for package in packages:
        print(f"\nInstalling '{package}'...")
        ok, err = _run_cmd([sys.executable, "-m", "pip", "install", package], package)
        if not ok:
            print(f"[*] Retrying '{package}' with --no-cache-dir...")
            ok, err = _run_cmd([sys.executable, "-m", "pip", "install", "--no-cache-dir", package], package)
        if ok:
            print(f"Success: '{package}' installed correctly.")
        else:
            failed_items.append(f"package:{package}")
            print_error(f"ERROR: Failed to install '{package}'. Details: {err}")

    # Download spacy models from the internet
    for model in spacy_models:
        print(f"\nDownloading spacy model '{model}' from the internet...")
        ok, err = _run_cmd([sys.executable, "-m", "spacy", "download", model], model)
        if ok:
            print(f"Success: '{model}' downloaded and installed correctly.")
        else:
            failed_items.append(f"spacy:{model}")
            print_error(f"ERROR: Failed to download spacy model '{model}'. Details: {err}")

    # Install Playwright browsers
    print("\nInstalling Playwright Chromium browser...")
    ok, err = _run_cmd([sys.executable, "-m", "playwright", "install", "chromium"], "playwright-chromium")
    if ok:
        print("Success: Playwright Chromium browser installed correctly.")
    else:
        failed_items.append("playwright:chromium")
        print_error(f"ERROR: Failed to install Playwright Chromium browser. Details: {err}")

    print("-" * 50)
    if failed_items:
        print_error(f"Installation finished with {len(failed_items)} failure(s): {', '.join(failed_items)}")
        return 1

    print("All Python libraries and spacy models have been successfully installed!")
    return 0


def main() -> int:
    """Entry point delegating to install_packages()."""
    return install_packages()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[*] Installation interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print_error(f"Fatal error: {e}")
        sys.exit(1)
