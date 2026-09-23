import os
import pandas as pd
from fpdf import FPDF

# Constantes de configuração
SUPPORTED_EXTENSIONS = ('.xls', '.xlsx', '.xlsm', '.ods', '.odf')
MAX_COLUMN_WIDTH = 200
BASE_CHAR_WIDTH_MM = 2.5
CELL_MARGIN_MM = 4
FONT_ARIAL_REGULAR = "C:\\Windows\\Fonts\\arial.ttf"
FONT_ARIAL_BOLD = "C:\\Windows\\Fonts\\arialbd.ttf"

def get_col_widths(df):
    widths = []
    for col in df.columns:
        max_len = len(str(col))
        if not df[col].empty:
            col_max_len = df[col].apply(lambda x: len(str(x))).max()
            max_len = max(max_len, col_max_len)
        widths.append(max_len * BASE_CHAR_WIDTH_MM + CELL_MARGIN_MM)
    return widths

def get_excel_files(folder_path):
    return [f for f in os.listdir(folder_path) if f.lower().endswith(SUPPORTED_EXTENSIONS)]

def setup_fonts(pdf):
    if os.path.exists(FONT_ARIAL_REGULAR):
        pdf.add_font("Arial", "", FONT_ARIAL_REGULAR)
        if os.path.exists(FONT_ARIAL_BOLD):
            pdf.add_font("Arial", "B", FONT_ARIAL_BOLD)
        return "Arial"
    return "helvetica"

def clean_column_names(df):
    df.columns = [col if not str(col).startswith('Unnamed') else '' for col in df.columns]

def calculate_sheet_dimensions(df, col_widths):
    total_width = sum(col_widths) + 20
    total_height = (len(df) + 2) * 8 + 30
    
    total_width = max(total_width, 100)
    total_height = max(total_height, 100)
    
    return total_width, total_height

def write_sheet_to_pdf(pdf, file_name, sheet_name, df, font_name):
    clean_column_names(df)
    
    col_widths = get_col_widths(df)
    col_widths = [min(w, MAX_COLUMN_WIDTH) for w in col_widths] 
    
    total_width, total_height = calculate_sheet_dimensions(df, col_widths)
    
    pdf.add_page(format=(total_width, total_height))
    
    pdf.set_font(font_name, style="B", size=14)
    pdf.cell(0, 10, text=f"Planilha: {file_name} - Aba: {sheet_name}", new_x="LMARGIN", new_y="NEXT", align="L")
    pdf.ln(5)
    
    pdf.set_font(font_name, size=10)
    with pdf.table(col_widths=col_widths, text_align="LEFT", width=sum(col_widths)) as table:
        row = table.row()
        for col in df.columns:
            row.cell(str(col))
        
        for _, data_row in df.iterrows():
            row = table.row()
            for item in data_row:
                val = "" if pd.isna(item) else str(item)
                row.cell(val)

def process_single_file(folder_path, file_name):
    file_path = os.path.join(folder_path, file_name)
    pdf_path = os.path.join(folder_path, os.path.splitext(file_name)[0] + ".pdf")
    
    if os.path.exists(pdf_path):
        print(f"\nPulando arquivo: {file_name} (PDF já existe)")
        return
        
    print(f"\nProcessando arquivo: {file_name}")
    
    try:
        sheets_dict = pd.read_excel(file_path, sheet_name=None)
        pdf = FPDF()
        font_name = setup_fonts(pdf)
        has_content = False
        
        for sheet_name, df in sheets_dict.items():
            if df.empty and df.columns.empty:
                print(f"  Aba '{sheet_name}' vazia. Ignorando.")
                continue
            
            print(f"  Transformando aba: {sheet_name}")
            has_content = True
            
            write_sheet_to_pdf(pdf, file_name, sheet_name, df, font_name)

        if has_content:
            pdf.output(pdf_path)
            print(f"-> Salvo: {os.path.basename(pdf_path)}")
        else:
            print(f"O arquivo {file_name} não continha dados válidos em nenhuma aba.")
            
    except Exception as e:
        print(f"  Erro ao processar {file_name}: {e}")

def export_to_pdf_pure_python(folder_path):
    files = get_excel_files(folder_path)
    
    if not files:
        print("Nenhum arquivo de planilha encontrado.")
        return

    for file_name in files:
        process_single_file(folder_path, file_name)

if __name__ == "__main__":
    export_to_pdf_pure_python(os.getcwd())
