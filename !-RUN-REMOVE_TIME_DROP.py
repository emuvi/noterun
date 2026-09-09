import os
import re
import sys
import shutil
import traceback
from datetime import datetime
from typing import Optional, Tuple, List

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

# Global event chain to track execution trace for each file
event_chain: List[str] = []

# --- Visualization and Logging Helpers ---

def get_current_time() -> str:
    try:
        return datetime.now().strftime('%H:%M:%S')
    except Exception as e:
        print(f"🔴 [ERROR] [get_current_time] get_current_time failed: {e}")
        return "00:00:00"

def log_info(func_name: str, message: str) -> None:
    try:
        msg = f"[{get_current_time()}] ℹ️ [LOG] [{func_name}] {message}"
        print(msg)
        event_chain.append(msg)
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [ERROR] [log_info] log_info failed: {e}")

def log_step(func_name: str, message: str) -> None:
    try:
        msg = f"[{get_current_time()}] 🔹 [STEP] [{func_name}] {message}"
        print(msg)
        event_chain.append(msg)
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [ERROR] [log_step] log_step failed: {e}")

def log_success(func_name: str, message: str) -> None:
    try:
        msg = f"[{get_current_time()}] ✅ [SUCCESS] [{func_name}] {message}"
        print(msg)
        event_chain.append(msg)
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [ERROR] [log_success] log_success failed: {e}")

def log_error(func_name: str, message: str) -> None:
    try:
        msg = f"[{get_current_time()}] 🔴 [ERROR] [{func_name}] {message}"
        print(msg)
        event_chain.append(msg)
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [ERROR] [log_error] log_error failed: {e}")

def print_summary_box(title: str, total: int, success: int, fails: int) -> None:
    func_name = "print_summary_box"
    try:
        box_width = 50
        lines = [
            "\n" + "╔" + "═" * (box_width - 2) + "╗",
            "║" + f"{title}".center(box_width - 2) + "║",
            "╠" + "═" * (box_width - 2) + "╣",
            "║" + f"Total Processed: {total}".ljust(box_width - 2) + "║",
            "║" + f"Successes:       {success}".ljust(box_width - 2) + "║",
            "║" + f"Failures:        {fails}".ljust(box_width - 2) + "║",
            "╚" + "═" * (box_width - 2) + "╝\n"
        ]
        for line in lines:
            print(line)
        event_chain.extend(lines)
    except Exception as e:
        log_error(func_name, f"Failed to print summary box: {e}")

def handle_file_error(file_path: str, current_dir: str, error_log: str) -> None:
    func_name = "handle_file_error"
    log_step(func_name, f"Starting - Parameters: file_path={file_path}")
    log_step(func_name, f"Moving '{file_path}' to '!-ERRORS'...")
    base_name, ext = os.path.splitext(file_path)
    errors_dir = os.path.join(current_dir, "!-ERRORS")
    os.makedirs(errors_dir, exist_ok=True)
    error_path = os.path.join(errors_dir, file_path)

    try:
        shutil.move(os.path.join(current_dir, file_path), error_path)
        log_success(func_name, f"Moved main file to '!-ERRORS'")
        
        # Save the error log
        log_file_path = os.path.join(errors_dir, f"{base_name}.log")
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(event_chain) + "\n\n[FINAL ERROR]\n" + error_log)
        log_success(func_name, f"Saved error log to '{log_file_path}'")
    except Exception as e:
        log_error(func_name, f"Failed to move main file {file_path}: {e}")

# --- Time Removal Logic ---

def parse_date_prefix(filename: str) -> Tuple[Optional[datetime], str, Optional[str]]:
    formats = [
        "%Y.%m.%d-%H.%M", "%Y.%m.%d_%H.%M.%S", "%Y-%m-%d_%H-%M-%S", "%Y.%m.%d %H.%M.%S",
        "%Y-%m-%d %H:%M:%S", "%Y.%m.%d-%H.%M.%S", "%Y.%m.%d",
        "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y",
        "%Y%m%d_%H%M%S", "%Y%m%d",
        "%Y.%m.%d %H.%M", "%Y-%m-%d %H.%M", "%Y-%m-%d_%H.%M",
        "%Y%m%d%H%M%S", "%Y%m%d%H%M"
    ]
    
    for length in range(25, 7, -1):
        if length > len(filename):
            continue
        prefix = filename[:length]
        for fmt in formats:
            try:
                dt = datetime.strptime(prefix, fmt)
                rest = filename[length:]
                
                if rest.startswith(' - '):
                    return dt, rest[3:], fmt
                elif rest.startswith('- ') or rest.startswith(' -'):
                    return dt, rest[2:], fmt
                elif rest.startswith(' ') or rest.startswith('-') or rest.startswith('_'):
                    return dt, rest[1:], fmt
                else:
                    return dt, rest, fmt
            except ValueError:
                continue
    return None, filename, None

def remove_time_from_filename(filename: str) -> Tuple[Optional[str], Optional[str]]:
    # Check if there's a user prefix like "[ PREFIX ] - "
    match = re.match(r"^(\[ .*? \] - )(.*)$", filename)
    if match:
        prefix_part = match.group(1)
        name_to_parse = match.group(2)
    else:
        prefix_part = ""
        name_to_parse = filename
        
    dt, rest_part, fmt = parse_date_prefix(name_to_parse)
    if dt:
        if not rest_part:
            return None, "Removing time would leave file without name/extension"
        return f"{prefix_part}{rest_part}", None
        
    return None, "No matching time format found in filename"

def get_safe_target_path(directory: str, filename: str) -> str:
    target_path = os.path.join(directory, filename)
    name_part, ext = os.path.splitext(filename)
    counter = 1
    
    while os.path.exists(target_path):
        new_name = f"{name_part} ({counter}){ext}"
        target_path = os.path.join(directory, new_name)
        counter += 1
        
    return target_path

# --- UI and Drop Event Handling ---

class DropZone(QLabel):
    def __init__(self) -> None:
        func_name = "DropZone.__init__"
        try:
            log_step(func_name, "Initializing DropZone widget.")
            super().__init__()
            self.session_success_count = 0
            self.session_fail_count = 0
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setText(
                "Drag and Drop File(s) Here\n\n🔹 Action: Remove Time from Filename\n(Removes date/time prefix from the filename)")
            self.setStyleSheet('''
                QLabel {
                    border: 4px dashed #aaa;
                    font-size: 24px;
                    color: #555;
                    background-color: #f9f9f9;
                    border-radius: 10px;
                    margin: 20px;
                }
            ''')
            self.setAcceptDrops(True)
            log_success(func_name, "DropZone widget initialized successfully.")
        except Exception as e:
            log_error(func_name, f"Error initializing DropZone: {e}")

    def dragEnterEvent(self, a0: Optional[QDragEnterEvent]) -> None:
        func_name = "DropZone.dragEnterEvent"
        try:
            if a0 is None:
                return

            mime_data = a0.mimeData()
            if mime_data is not None and mime_data.hasUrls():
                a0.accept()
                return
            a0.ignore()
        except Exception as e:
            log_error(func_name, f"Error in dragEnterEvent: {e}")
            if a0 is not None:
                a0.ignore()

    def dropEvent(self, a0: Optional[QDropEvent]) -> None:
        func_name = "DropZone.dropEvent"
        try:
            log_step(func_name, "Drop event triggered.")
            if a0 is None:
                log_error(func_name, "Received None for dropEvent. Ignoring.")
                return

            mime_data = a0.mimeData()
            if mime_data is not None and mime_data.hasUrls():
                urls = mime_data.urls()
                for url in urls:
                    file_path = url.toLocalFile()
                    if os.path.isfile(file_path):
                        log_success(func_name, f"Valid file dropped: {file_path}")
                        self.process_file(file_path)
                    else:
                        log_error(func_name, f"Dropped item is not a valid file: {file_path}")
        except Exception as e:
            log_error(func_name, f"Error in dropEvent: {e}")

    def process_file(self, file_path: str) -> None:
        func_name = "DropZone.process_file"
        event_chain.clear()
        log_step("Cycle", f"Processing dropped file: {file_path}")
        cycle_success = 0
        cycle_fail = 0

        try:
            filename = os.path.basename(file_path)
            directory = os.path.dirname(file_path)
            new_name, skip_reason = remove_time_from_filename(filename)
            
            if not new_name:
                log_info(func_name, f"No changes needed for '{filename}': {skip_reason}")
                cycle_success = 1
            else:
                new_filepath = get_safe_target_path(directory, new_name)
                log_step(func_name, f"Renaming to '{os.path.basename(new_filepath)}'")
                
                try:
                    os.rename(file_path, new_filepath)
                    log_success(func_name, f"Successfully renamed file.")
                    cycle_success = 1
                except Exception as rename_e:
                    error_msg = f"Failed to rename file: {rename_e}"
                    log_error(func_name, error_msg)
                    handle_file_error(filename, directory, error_msg)
                    cycle_fail = 1

            self.session_success_count += cycle_success
            self.session_fail_count += cycle_fail
            session_total = self.session_success_count + self.session_fail_count

            print_summary_box("Cycle Summary", 1, cycle_success, cycle_fail)
            print_summary_box("Processing Summary", session_total, self.session_success_count, self.session_fail_count)

        except Exception as e:
            error_msg = f"Critical error processing dropped file: {e}\n{traceback.format_exc()}"
            log_error(func_name, error_msg)
            handle_file_error(os.path.basename(file_path), os.path.dirname(file_path), error_msg)
            
            cycle_fail = 1
            self.session_fail_count += cycle_fail
            session_total = self.session_success_count + self.session_fail_count
            
            print_summary_box("Cycle Summary (Interrupted)", 1, 0, cycle_fail)
            print_summary_box("Processing Summary (Interrupted)", session_total, self.session_success_count, self.session_fail_count)

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        func_name = "MainWindow.__init__"
        try:
            log_step(func_name, "Initializing MainWindow.")
            super().__init__()
            self.setWindowTitle("Remove Time from Filename Drop & Execute")
            self.resize(600, 400)

            log_step(func_name, "Setting up central widget and layout.")
            self.central_widget = QWidget()
            self.setCentralWidget(self.central_widget)

            layout = QVBoxLayout()

            self.drop_zone = DropZone()
            layout.addWidget(self.drop_zone)

            self.central_widget.setLayout(layout)
            log_success(func_name, "MainWindow initialized successfully.")
        except Exception as e:
            log_error(func_name, f"Error initializing MainWindow: {e}")

def main() -> None:
    func_name = "main"
    log_step(func_name, "Application entry point reached.")
    
    try:
        log_step(func_name, "Initializing QApplication.")
        app = QApplication(sys.argv)

        log_step(func_name, "Creating MainWindow instance.")
        window = MainWindow()
        window.show()

        log_success(func_name, "Application started successfully. Waiting for file drops...")
        sys.exit(app.exec_())
    except Exception as e:
        log_error(func_name, f"Error in main application loop: {e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"[{get_current_time()}] 🔴 [ERROR] [main] Process interrupted by user. Exiting.")
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [ERROR] [main] Fatal error: {e}")
