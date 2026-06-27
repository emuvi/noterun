import subprocess
import sys
import os


def install_packages():
    """Install required Python packages from the internet."""
    packages = [
        "PyPDF2",
        "lmstd",
        "PyQt5"
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

    print("-" * 50)
    print("All Python libraries have been successfully installed!")
    return True


if __name__ == "__main__":
    install_packages()
    print("\nPress Enter to exit...")
    input()
