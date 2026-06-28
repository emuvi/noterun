import subprocess
import sys
import os


def install_packages():
    """Install required Python packages and spacy models from the internet."""
    packages = [
        "PyQt5",
        "PyPDF2",
        "lmstd",
        "click",
        "spacy",
        "langdetect"
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

    print("Starting the installation of required libraries...")
    print("-" * 50)

    # Update pip first to avoid warnings
    try:
        print("Updating pip...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    except subprocess.CalledProcessError:
        print("Warning: Could not update pip, continuing with installation...")

    # Install packages
    for package in packages:
        try:
            print(f"\nInstalling '{package}'...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", package])
            print(f"Success: '{package}' installed correctly.")
        except subprocess.CalledProcessError as e:
            print(f"\nERROR: Failed to install '{package}'. Details: {e}")
            return False

    # Download spacy models from the internet
    for model in spacy_models:
        try:
            print(f"\nDownloading spacy model '{model}' from the internet...")
            subprocess.check_call(
                [sys.executable, "-m", "spacy", "download", model])
            print(f"Success: '{model}' downloaded and installed correctly.")
        except subprocess.CalledProcessError as e:
            print(
                f"\nERROR: Failed to download spacy model '{model}'. Details: {e}")
            return False

    print("-" * 50)
    print("All Python libraries and spacy models have been successfully installed!")
    return True


if __name__ == "__main__":
    install_packages()
    print("\nPress Enter to exit...")
    input()
