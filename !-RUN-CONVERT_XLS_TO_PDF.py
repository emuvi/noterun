import os
import sys
import time
import warnings
from datetime import datetime
import traceback

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

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

try:
    import pandas as pd
    from fpdf import FPDF
except ImportError as e:
    print(f"🔴 [ERROR] Required library missing: {e}. Install with: pip install pandas fpdf2 openpyxl xlrd odfpy", file=sys.stderr)
    sys.exit(1)

# Constantes de configuração
SUPPORTED_EXTENSIONS = ('.xls', '.xlsx', '.xlsm', '.ods', '.odf', '.csv')
MAX_COLUMN_WIDTH = 200
BASE_CHAR_WIDTH_MM = 2.5
CELL_MARGIN_MM = 4
FONT_ARIAL_REGULAR = "C:\\Windows\\Fonts\\arial.ttf"
FONT_ARIAL_BOLD = "C:\\Windows\\Fonts\\arialbd.ttf"

# ==============================================================================
# GLOBAL CONFIGURATION
# ==============================================================================
# Determines whether to delete origin files after processing.
# True  -> Deletes the files automatically without asking.
# False -> Keeps the files without asking.
# None  -> Prompts the user to decide.
DELETE_ORIGIN_FILES = None
# ==============================================================================

def get_current_time():
    """
    Returns the current time formatted as HH:MM:SS.
    
    Returns:
        str: The current time string.
    """
    return datetime.now().strftime("%H:%M:%S")

def print_log(emoji, category, function_name, message):
    """
    Prints a formatted log message following the required pattern.
    
    Args:
        emoji (str): The emoji indicator (e.g., ℹ️, 🔹, ✅, 🔴).
        category (str): The category of the log (e.g., LOG, STEP, SUCCESS, ERROR).
        function_name (str): The name of the function or step.
        message (str): The message to log.
    """
    stream = sys.stderr if category == "ERROR" else sys.stdout
    print(f"[{get_current_time()}] {emoji} [{category}] [{function_name}] {message}", file=stream)

def get_col_widths(df):
    """
    Calculates the required width for each column in a DataFrame based on content.
    
    Args:
        df (pd.DataFrame): The DataFrame to analyze.
        
    Returns:
        list: A list of column widths in mm.
        
    Raises:
        Exception: If column width calculation fails due to incompatible data types.
    """
    print_log("🔹", "STEP", "get_col_widths", f"Starting with df of shape {df.shape}")
    widths = []
    try:
        for col in df.columns:
            max_len = len(str(col))
            if not df[col].empty:
                col_max_len = df[col].apply(lambda x: len(str(x))).max()
                max_len = max(max_len, col_max_len)
            widths.append(max_len * BASE_CHAR_WIDTH_MM + CELL_MARGIN_MM)
        print_log("✅", "SUCCESS", "get_col_widths", "Completed calculating widths")
        return widths
    except Exception as e:
        print_log("🔴", "ERROR", "get_col_widths", f"Failed to calculate column widths: {e}. Fix by checking DataFrame content types.")
        raise

def get_excel_files(folder_path):
    """
    Gets a list of all supported Excel files in the given folder.
    
    Args:
        folder_path (str): The path to search for files.
        
    Returns:
        list: A list of file names that match supported extensions.
        
    Raises:
        Exception: If directory access fails or path is invalid.
    """
    print_log("🔹", "STEP", "get_excel_files", f"Starting search in {folder_path}")
    try:
        files = [f for f in os.listdir(folder_path) if f.lower().endswith(SUPPORTED_EXTENSIONS)]
        print_log("✅", "SUCCESS", "get_excel_files", f"Completed finding {len(files)} files")
        return files
    except Exception as e:
        print_log("🔴", "ERROR", "get_excel_files", f"Failed to list files: {e}. Fix by checking directory permissions or path validity.")
        raise

def setup_fonts(pdf):
    """
    Configures fonts for the PDF generation, preferring Arial if available.
    Falls back to helvetica if Arial cannot be loaded.
    """
    print_log("🔹", "STEP", "setup_fonts", "Starting font configuration")
    try:
        if os.path.exists(FONT_ARIAL_REGULAR):
            pdf.add_font("Arial", "", FONT_ARIAL_REGULAR)
            if os.path.exists(FONT_ARIAL_BOLD):
                pdf.add_font("Arial", "B", FONT_ARIAL_BOLD)
            print_log("✅", "SUCCESS", "setup_fonts", "Completed font configuration using Arial")
            return "Arial"
    except Exception as e:
        print_log("ℹ️", "LOG", "setup_fonts", f"Arial font unavailable ({e}); falling back to helvetica.")
    print_log("✅", "SUCCESS", "setup_fonts", "Completed font configuration using helvetica fallback")
    return "helvetica"


def _safe_pdf_text(text: str, font_name: str) -> str:
    """Ensures text is compatible with the selected PDF font."""
    if font_name == "helvetica":
        return text.encode("latin-1", errors="replace").decode("latin-1")
    return text

def clean_column_names(df):
    """
    Removes 'Unnamed' column headers generated by pandas for empty headers.
    
    Args:
        df (pd.DataFrame): The DataFrame to clean.
        
    Raises:
        Exception: If DataFrame column names cannot be modified or accessed.
    """
    print_log("🔹", "STEP", "clean_column_names", "Starting to clean column names")
    try:
        df.columns = [col if not str(col).startswith('Unnamed') else '' for col in df.columns]
        print_log("✅", "SUCCESS", "clean_column_names", "Completed cleaning column names")
    except Exception as e:
        print_log("🔴", "ERROR", "clean_column_names", f"Failed to clean column names: {e}. Fix by validating DataFrame columns.")
        raise

def calculate_sheet_dimensions(df, col_widths):
    """
    Calculates the total width and height required for the PDF page.
    
    Args:
        df (pd.DataFrame): The DataFrame to be written.
        col_widths (list): The list of column widths.
        
    Returns:
        tuple: (total_width, total_height) for the PDF page.
        
    Raises:
        Exception: If calculations fail due to invalid width data or DataFrame length.
    """
    print_log("🔹", "STEP", "calculate_sheet_dimensions", "Starting dimension calculation")
    try:
        total_width = sum(col_widths) + 20
        total_height = 30  # Title and margins
        
        # Calculate header height
        header_lines = 1
        for i, col in enumerate(df.columns):
            text_w = len(str(col)) * BASE_CHAR_WIDTH_MM + CELL_MARGIN_MM
            w = max(col_widths[i], 1.0) if i < len(col_widths) else 10.0
            lines = int(text_w / w) + str(col).count('\n') + 1
            if lines > header_lines:
                header_lines = lines
        total_height += (header_lines * 8) + 2
        
        # Calculate data rows height
        for _, data_row in df.iterrows():
            row_lines = 1
            for i, item in enumerate(data_row):
                val = "" if pd.isna(item) else str(item)
                text_w = len(val) * BASE_CHAR_WIDTH_MM + CELL_MARGIN_MM
                w = max(col_widths[i], 1.0) if i < len(col_widths) else 10.0
                lines = int(text_w / w) + val.count('\n') + 1
                if lines > row_lines:
                    row_lines = lines
            total_height += (row_lines * 8) + 2
        
        total_width = max(total_width, 100)
        total_height = max(total_height, 100)
        
        # Avoid exceeding maximum PDF page limits (~5080mm)
        total_width = min(total_width, 5000)
        total_height = min(total_height, 5000)
        
        print_log("✅", "SUCCESS", "calculate_sheet_dimensions", f"Completed: width={total_width}, height={total_height}")
        return total_width, total_height
    except Exception as e:
        print_log("🔴", "ERROR", "calculate_sheet_dimensions", f"Failed to calculate dimensions: {e}. Fix by checking width array.")
        raise

def write_sheet_to_pdf(pdf, file_name, sheet_name, df, font_name):
    """
    Writes a single DataFrame sheet to the PDF instance.
    
    Args:
        pdf (FPDF): The PDF instance.
        file_name (str): The name of the source file.
        sheet_name (str): The name of the sheet being written.
        df (pd.DataFrame): The DataFrame contents.
        font_name (str): The font family to use.
        
    Raises:
        Exception: If PDF operations fail, such as adding pages or drawing tables.
    """
    print_log("🔹", "STEP", "write_sheet_to_pdf", f"Starting write for sheet: {sheet_name}")
    try:
        clean_column_names(df)
        
        col_widths = get_col_widths(df)
        col_widths = [min(w, MAX_COLUMN_WIDTH) for w in col_widths] 
        
        total_width, total_height = calculate_sheet_dimensions(df, col_widths)
        
        pdf.add_page(format=(total_width, total_height))
        
        pdf.set_font(font_name, style="B", size=14)
        pdf.cell(0, 10, text=_safe_pdf_text(f"Planilha: {file_name} - Aba: {sheet_name}", font_name), new_x="LMARGIN", new_y="NEXT", align="L")
        pdf.ln(5)
        
        pdf.set_font(font_name, size=10)
        with pdf.table(col_widths=col_widths, text_align="LEFT") as table:
            row = table.row()
            for col in df.columns:
                row.cell(_safe_pdf_text(str(col), font_name))
            
            for _, data_row in df.iterrows():
                row = table.row()
                for item in data_row:
                    val = "" if pd.isna(item) else str(item)
                    row.cell(_safe_pdf_text(val, font_name))
        
        print_log("✅", "SUCCESS", "write_sheet_to_pdf", f"Completed writing sheet {sheet_name}")
    except Exception as e:
        print_log("🔴", "ERROR", "write_sheet_to_pdf", f"Failed to write sheet {sheet_name}: {e}. Fix by checking DataFrame content and FPDF capabilities.")
        raise

def read_tabular_file(file_path):
    """Reads a CSV table or all sheets from a spreadsheet using fallback engines."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".csv":
        try:
            df = pd.read_csv(file_path, sep=None, engine="python", encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, sep=None, engine="python", encoding="cp1252")
        return {os.path.splitext(os.path.basename(file_path))[0]: df}

    engines = [None]
    if ext in (".xlsx", ".xlsm"):
        engines.extend(["openpyxl", "xlrd"])
    elif ext == ".xls":
        engines.extend(["xlrd", "openpyxl"])
    elif ext in (".ods", ".odf"):
        engines.append("odf")

    last_error = None
    for engine in engines:
        try:
            if engine is None:
                return pd.read_excel(file_path, sheet_name=None)
            return pd.read_excel(file_path, sheet_name=None, engine=engine)
        except Exception as e:
            last_error = e
            continue
    raise last_error


def process_single_file(folder_path, file_name):
    """
    Processes a single Excel file and converts it to PDF.
    
    Args:
        folder_path (str): The path containing the file.
        file_name (str): The file to process.
        
    Returns:
        tuple: (bool success, bool converted).
    """
    print_log("🔹", "STEP", "process_single_file", "Starting")
    print_log("ℹ️", "LOG", "process_single_file", f"Processing: {file_name} with specific_parameters folder_path={folder_path}")
    
    file_path = os.path.join(folder_path, file_name)
    pdf_path = os.path.join(folder_path, os.path.splitext(file_name)[0] + ".pdf")
    
    if os.path.exists(pdf_path):
        print_log("ℹ️", "LOG", "process_single_file", f"Skipping {file_name} (PDF already exists)")
        print_log("✅", "SUCCESS", "process_single_file", f"Completed skipping {file_name}")
        return True, False
        
    try:
        sheets_dict = read_tabular_file(file_path)
        pdf = FPDF()
        font_name = setup_fonts(pdf)
        has_content = False
        sheet_errors = 0
        
        for sheet_name, df in sheets_dict.items():
            if df.empty and df.columns.empty:
                print_log("ℹ️", "LOG", "process_single_file", f"Sheet '{sheet_name}' is empty. Ignoring.")
                continue
            
            try:
                write_sheet_to_pdf(pdf, file_name, sheet_name, df, font_name)
                has_content = True
            except Exception as sheet_err:
                sheet_errors += 1
                print_log("🔴", "ERROR", "process_single_file", f"Skipping sheet '{sheet_name}' in {file_name} due to error: {sheet_err}")

        if has_content:
            pdf.output(pdf_path)
            print_log("✅", "SUCCESS", "process_single_file", f"Completed saving: {os.path.basename(pdf_path)}")
            return sheet_errors == 0, True
        elif sheet_errors > 0:
            return False, False
        else:
            print_log("ℹ️", "LOG", "process_single_file", f"File {file_name} didn't contain valid data in any sheet.")
            print_log("✅", "SUCCESS", "process_single_file", f"Completed processing empty file {file_name}")
            return True, False
            
    except Exception as e:
        print_log("🔴", "ERROR", "process_single_file", f"Failed to process {file_name}: {e}. Fix by validating file integrity and permissions.")
        log_file_name = os.path.splitext(file_name)[0] + ".log"
        log_path = os.path.join(folder_path, log_file_name)
        try:
            with open(log_path, "w", encoding="utf-8") as log_file:
                log_file.write(f"--- Error Log for {file_name} ---\n")
                log_file.write(f"Time: {get_current_time()}\n\n")
                log_file.write("--- Error Details ---\n")
                log_file.write(f"{traceback.format_exc()}\n")
                log_file.write("--- Parameters Used ---\n")
                log_file.write(f"folder_path: {folder_path}\n")
                log_file.write(f"file_name: {file_name}\n")
                log_file.write(f"MAX_COLUMN_WIDTH: {MAX_COLUMN_WIDTH}\n")
                log_file.write(f"BASE_CHAR_WIDTH_MM: {BASE_CHAR_WIDTH_MM}\n")
                log_file.write(f"CELL_MARGIN_MM: {CELL_MARGIN_MM}\n")
                log_file.write(f"SUPPORTED_EXTENSIONS: {SUPPORTED_EXTENSIONS}\n")
                log_file.write(f"FONT_ARIAL_REGULAR: {FONT_ARIAL_REGULAR}\n")
                log_file.write(f"FONT_ARIAL_BOLD: {FONT_ARIAL_BOLD}\n")
        except Exception as log_e:
            print_log("🔴", "ERROR", "process_single_file", f"Failed to save error log for {file_name}: {log_e}")
        return False, False

def main():
    """
    Main orchestrator function for the PDF conversion script.
    
    Returns:
        int: 0 on success, 1 on failure.
    """
    print_log("🔹", "STEP", "main", "Starting XLS to PDF Conversion Script")
    folder_path = os.getcwd()
    print_log("ℹ️", "LOG", "main", f"Resolved runtime context. Target directory: {folder_path}")
    
    try:
        files = get_excel_files(folder_path)
    except Exception as e:
        print_log("🔴", "ERROR", "main", f"Could not gather work items: {e}")
        return 1
    
    if not files:
        print_log("ℹ️", "LOG", "main", "No spreadsheet files found to process.")
        return 0
        
    successes = 0
    failures = 0
    total = len(files)
    processed_files = []

    for i, file_name in enumerate(files, 1):
        print_log("🔹", "STEP", "main", f"Processing item {i} of {total}")
        success, converted = process_single_file(folder_path, file_name)
        if success:
            successes += 1
            if converted:
                processed_files.append(file_name)
        else:
            failures += 1

    # End of cycle: Summary with totals
    print_log("✅", "SUCCESS", "main", f"Completed cycle. Successes: {successes}, Failures: {failures}")

    # Visual Summary Box
    box_width = 50
    inner_width = box_width - 2
    
    summary_box = (
        f"╔{'═' * inner_width}╗\n"
        f"║{'Processing Summary'.center(inner_width)}║\n"
        f"╠{'═' * inner_width}╣\n"
        f"║ {f'Total Processed: {total}'.ljust(inner_width - 2)} ║\n"
        f"║ {f'Successes:       {successes}'.ljust(inner_width - 2)} ║\n"
        f"║ {f'Failures:        {failures}'.ljust(inner_width - 2)} ║\n"
        f"╚{'═' * inner_width}╝"
    )
    print(summary_box)
    
    if processed_files:
        if DELETE_ORIGIN_FILES is True:
            ans = 'y'
        elif DELETE_ORIGIN_FILES is False:
            ans = 'n'
        else:
            try:
                ans = read_input("\nDo you want to delete the origin files? (Y/N): ")
            except (EOFError, KeyboardInterrupt):
                ans = 'n'
            
        if ans.strip().lower() == 'y':
            for file_name in processed_files:
                file_path = os.path.join(folder_path, file_name)
                deleted = False
                last_err = None
                for attempt in range(1, 4):
                    try:
                        os.remove(file_path)
                        print(f"[+] Origin file deleted: {file_name}")
                        deleted = True
                        break
                    except Exception as e:
                        last_err = e
                        if attempt < 3:
                            time.sleep(0.4 * attempt)
                if not deleted:
                    failures += 1
                    print_log("🔴", "ERROR", "main", f"Error deleting {file_name}: {last_err}")

    return 1 if failures > 0 else 0

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[*] Process interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print_log("🔴", "ERROR", "main", f"Fatal error: {e}")
        sys.exit(1)
