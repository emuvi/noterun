import os
import pandas as pd
from fpdf import FPDF
import math

def get_col_widths(df):
    widths = []
    for col in df.columns:
        max_len = len(str(col))
        if not df[col].empty:
            col_max_len = df[col].apply(lambda x: len(str(x))).max()
            max_len = max(max_len, col_max_len)
        # Aproximação: 2.5 mm por caractere + margem de célula
        widths.append(max_len * 2.5 + 4)
    return widths

def export_to_pdf_pure_python(folder_path):
    extensions = ('.xls', '.xlsx', '.xlsm', '.ods', '.odf')
    files = [f for f in os.listdir(folder_path) if f.lower().endswith(extensions)]
    
    if not files:
        print("Nenhum arquivo de planilha encontrado.")
        return

    for file in files:
        file_path = os.path.join(folder_path, file)
        pdf_path = os.path.join(folder_path, os.path.splitext(file)[0] + ".pdf")
        
        print(f"\nProcessando arquivo: {file}")
        
        try:
            # Lendo todas as abas (retorna um dict de dataframes)
            # O pandas requer as bibliotecas xlrd, openpyxl, e odfpy para suportar todas as extensões
            sheets_dict = pd.read_excel(file_path, sheet_name=None)
            
            pdf = FPDF()
            
            # Tenta carregar a fonte Arial para suportar caracteres com acentos comuns
            font_path = "C:\\Windows\\Fonts\\arial.ttf"
            if os.path.exists(font_path):
                pdf.add_font("Arial", "", font_path)
                pdf.add_font("Arial", "B", "C:\\Windows\\Fonts\\arialbd.ttf")
                font_name = "Arial"
            else:
                font_name = "helvetica"
            
            has_content = False
            
            for sheet_name, df in sheets_dict.items():
                if df.empty and df.columns.empty:
                    print(f"  Aba '{sheet_name}' vazia. Ignorando.")
                    continue
                
                print(f"  Transformando aba: {sheet_name}")
                has_content = True
                
                # Tratar cabeçalhos vazios ou "Unnamed" gerados pelo pandas
                df.columns = [col if not str(col).startswith('Unnamed') else '' for col in df.columns]
                
                # Calcular largura e altura dinâmicas baseadas no conteúdo
                col_widths = get_col_widths(df)
                # Limitar largura para não quebrar a geração se houver texto imenso em uma célula
                col_widths = [min(w, 200) for w in col_widths] 
                
                total_width = sum(col_widths) + 20 # Margens direita e esquerda de 10mm
                total_height = (len(df) + 2) * 8 + 30 # Altura baseada em ~8mm por linha + margens superiores/inferiores
                
                # Garantir dimensões mínimas para a folha
                total_width = max(total_width, 100)
                total_height = max(total_height, 100)
                
                # Adiciona página com dimensões personalizadas para esta aba (exatamente o tamanho necessário)
                pdf.add_page(format=(total_width, total_height))
                
                # Título da Aba
                pdf.set_font(font_name, style="B", size=14)
                pdf.cell(0, 10, text=f"Planilha: {file} - Aba: {sheet_name}", new_x="LMARGIN", new_y="NEXT", align="L")
                pdf.ln(5)
                
                # Desenhar a tabela usando o contexto nativo do fpdf2
                pdf.set_font(font_name, size=10)
                with pdf.table(col_widths=col_widths, text_align="LEFT", width=sum(col_widths)) as table:
                    # Linha de cabeçalho
                    row = table.row()
                    for col in df.columns:
                        row.cell(str(col))
                    
                    # Linhas de dados
                    for _, data_row in df.iterrows():
                        row = table.row()
                        for item in data_row:
                            # Tratar NaN/Nat (nulos) como texto vazio
                            val = "" if pd.isna(item) else str(item)
                            row.cell(val)

            if has_content:
                pdf.output(pdf_path)
                print(f"-> Salvo: {os.path.basename(pdf_path)}")
            else:
                print(f"O arquivo {file} não continha dados válidos em nenhuma aba.")
                
        except Exception as e:
            print(f"  Erro ao processar {file}: {e}")

if __name__ == "__main__":
    export_to_pdf_pure_python(os.getcwd())
