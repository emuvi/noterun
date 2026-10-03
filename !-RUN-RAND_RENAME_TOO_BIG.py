import os
import random
import string


def get_random_name(length=18):
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for i in range(length))


def rename_files_in_directory():
    current_dir = os.getcwd()

    for filename in os.listdir(current_dir):
        file_path = os.path.join(current_dir, filename)

        if os.path.isfile(file_path):
            if filename.startswith("!-"):
                continue
            file_extension = os.path.splitext(filename)[1].lower()
            if file_extension != '.pdf':
                continue

            if os.path.getsize(file_path) > 300 * 1024 * 1024:
                too_big_dir = os.path.join(current_dir, 'Too Big')
                os.makedirs(too_big_dir, exist_ok=True)
                os.rename(file_path, os.path.join(too_big_dir, filename))
                print(f'Moved to Too Big: {filename}')
                continue

            new_name = "RAND " + get_random_name() + file_extension
            new_file_path = os.path.join(current_dir, new_name)

            os.rename(file_path, new_file_path)
            print(f'Renamed: {filename} -> {new_name}')


def main():
    proceed = input(
        "Do you want to proceed with random renaming all files in the current directory? (yes/no): ").strip().lower()
    if proceed == 'yes':
        rename_files_in_directory()
        print("Renaming completed.")
    else:
        print("Operation canceled.")


if __name__ == "__main__":
    main()
    input()
