import os
import io
import re
import sys
import unicodedata
from pathlib import Path
from pypdf import PdfReader
from datetime import datetime


FIELD_MARKERS = (
    "Status", "Resolução", "Origem", "Detalhes", "Descrição", "Sistema e Contrato",
    "Previsibilidade de Atendimento", "Cronograma de Compromissos", "Discussão",
    "Visão Geral", "Faturamento", "ESG", "Links", "Histórico", "Informação de Faturamento"
)


def get_current_time():
    """
    Returns the current timestamp in [HH:MM:SS] format.
    
    Returns:
        str: Current time formatted as [HH:MM:SS].
    """
    return f"[{datetime.now().strftime('%H:%M:%S')}]"


def normalize_pdf_text(text):
    """
    Converte quebras e caracteres invisíveis em espaços previsíveis.

    Parameters:
        text (str): The raw text extracted from the PDF.

    Returns:
        str: The normalized text with standard spaces.
    """
    print(f"{get_current_time()} 🔹 [STEP] [normalize_pdf_text] Starting with text length: {len(text)}")
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00ad", "").replace("\ufffd", " ")
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    result = re.sub(r"\s+", " ", text).strip()
    print(f"{get_current_time()} ✅ [SUCCESS] [normalize_pdf_text] Completed normalisation. New length: {len(result)}")
    return result


def clean_title(title):
    """
    Remove rótulos e pontuação residual sem destruir o título.

    Parameters:
        title (str): The extracted raw title.

    Returns:
        str: The cleaned title.
    """
    print(f"{get_current_time()} 🔹 [STEP] [clean_title] Starting with title: '{title}'")
    title = re.sub(r"^Título\s*:\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^\*\s*", "", title).strip(" -:;")
    result = re.sub(r"\s+", " ", title).strip()
    print(f"{get_current_time()} ✅ [SUCCESS] [clean_title] Completed. Cleaned title: '{result}'")
    return result


def _find_title_by_header(text, number, marker_end):
    """
    Busca o título usando o padrão de cabeçalho padrão.

    Parameters:
        text (str): The parsed text from the PDF.
        number (str): The demand number to anchor the search.
        marker_end (str): Regex pattern for the end of the field.

    Returns:
        str or None: The matched title, if found.
    """
    print(f"{get_current_time()} 🔹 [STEP] [_find_title_by_header] Starting for number: {number}")
    match = re.search(
        rf"(?:Demanda\s+)?{re.escape(number)}\s*:\s*(.+?){marker_end}",
        text,
        re.IGNORECASE,
    )
    if match:
        result = clean_title(match.group(1))
        print(f"{get_current_time()} ✅ [SUCCESS] [_find_title_by_header] Completed. Found: '{result}'")
        return result
    print(f"{get_current_time()} ℹ️ [LOG] [_find_title_by_header] No match found.")
    return None


def _find_title_by_id_only(text, number):
    """
    Busca o título considerando apenas o ID da demanda no texto.

    Parameters:
        text (str): The parsed text from the PDF.
        number (str): The demand number to anchor the search.

    Returns:
        str or None: The matched title, if found.
    """
    print(f"{get_current_time()} 🔹 [STEP] [_find_title_by_id_only] Starting for number: {number}")
    match = re.search(rf"\b{re.escape(number)}\s*:\s*(.{{1,300}})", text, re.IGNORECASE)
    if match:
        candidate = re.split(
            r"\s+(?:Status|Resolução|Origem|Detalhes)\s*:?",
            match.group(1),
            maxsplit=1,
            flags=re.IGNORECASE,
        )
        result = clean_title(candidate[0])
        print(f"{get_current_time()} ✅ [SUCCESS] [_find_title_by_id_only] Completed. Found: '{result}'")
        return result
    print(f"{get_current_time()} ℹ️ [LOG] [_find_title_by_id_only] No match found.")
    return None


def _find_title_by_ewm_format(text, marker_end):
    """
    Busca o título utilizando formato específico de exportações EWM.

    Parameters:
        text (str): The parsed text from the PDF.
        marker_end (str): Regex pattern for the end of the field.

    Returns:
        str or None: The matched title, if found.
    """
    print(f"{get_current_time()} 🔹 [STEP] [_find_title_by_ewm_format] Starting search")
    match = re.search(r"Título\s*:\s*\*?\s*(.+?)" + marker_end, text, re.IGNORECASE)
    if match:
        result = clean_title(match.group(1))
        print(f"{get_current_time()} ✅ [SUCCESS] [_find_title_by_ewm_format] Completed. Found: '{result}'")
        return result
    print(f"{get_current_time()} ℹ️ [LOG] [_find_title_by_ewm_format] No match found.")
    return None


def find_title(text, number):
    """
    Procura o título tanto no cabeçalho com ':' quanto no campo Título.

    Parameters:
        text (str): The complete parsed text from the PDF.
        number (str): The identified demand number.

    Returns:
        str or None: The title, if any strategy successfully extracts it.
    """
    print(f"{get_current_time()} 🔹 [STEP] [find_title] Starting execution for number: {number}")
    marker_end = r"(?=\s+(?:" + "|".join(map(re.escape, FIELD_MARKERS)) + r")\b|$)"
    result = (
        _find_title_by_header(text, number, marker_end) or
        _find_title_by_id_only(text, number) or
        _find_title_by_ewm_format(text, marker_end)
    )
    if result:
        print(f"{get_current_time()} ✅ [SUCCESS] [find_title] Completed. Found title: '{result}'")
    else:
        print(f"{get_current_time()} 🔴 [ERROR] [find_title] Failed to find title.")
    return result


def _find_number_by_pattern(text):
    """
    Tenta localizar o número usando padrões específicos de expressões regulares.

    Parameters:
        text (str): The PDF text to search.

    Returns:
        str or None: The matched demand number, if found.
    """
    print(f"{get_current_time()} 🔹 [STEP] [_find_number_by_pattern] Starting search")
    patterns = (
        r"^\s*(\d{7})\s*:",
        r"(?:Demanda|Item\s+de\s+Trabalho)\s*(\d{7})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result = match.group(1)
            print(f"{get_current_time()} ✅ [SUCCESS] [_find_number_by_pattern] Completed. Found: {result}")
            return result
    print(f"{get_current_time()} ℹ️ [LOG] [_find_number_by_pattern] No match found.")
    return None


def _find_number_by_fallback(text):
    """
    Fallback para PDFs que removem o rótulo, mas deixam o ID no cabeçalho.

    Parameters:
        text (str): The PDF text to search.

    Returns:
        str or None: The matched demand number, if found.
    """
    print(f"{get_current_time()} 🔹 [STEP] [_find_number_by_fallback] Starting search")
    for match in re.finditer(r"\b(\d{7})\b", text):
        value = match.group(1)
        context = text[max(0, match.start() - 20):match.start()].lower()
        if not re.search(r"(?:data|cpf|cnpj|processo|id)\s*$", context):
            print(f"{get_current_time()} ✅ [SUCCESS] [_find_number_by_fallback] Completed. Found: {value}")
            return value
    print(f"{get_current_time()} ℹ️ [LOG] [_find_number_by_fallback] No match found.")
    return None


def find_number(text):
    """
    Prioriza números no cabeçalho e evita confundir datas/IDs com a demanda.

    Parameters:
        text (str): The PDF text content.

    Returns:
        str or None: The extracted number, if found.
    """
    print(f"{get_current_time()} 🔹 [STEP] [find_number] Starting search")
    result = _find_number_by_pattern(text) or _find_number_by_fallback(text)
    if result:
        print(f"{get_current_time()} ✅ [SUCCESS] [find_number] Completed. Found number: {result}")
    else:
        print(f"{get_current_time()} 🔴 [ERROR] [find_number] Failed to find number.")
    return result


def extract_text_from_pdf(pdf_path):
    """
    Lê o conteúdo do PDF, limitado às primeiras 3 páginas.

    Parameters:
        pdf_path (Path): Path object to the PDF file.

    Returns:
        str: Raw text extracted from the PDF.
    """
    print(f"{get_current_time()} 🔹 [STEP] [extract_text_from_pdf] Starting reading: {pdf_path.name}")
    try:
        reader = PdfReader(pdf_path)
        result = "\n".join(
            page.extract_text()
            for page in reader.pages[:3]
            if page.extract_text()
        )
        print(f"{get_current_time()} ✅ [SUCCESS] [extract_text_from_pdf] Completed text extraction.")
        return result
    except Exception as e:
        print(f"{get_current_time()} 🔴 [ERROR] [extract_text_from_pdf] Failed to read PDF {pdf_path.name}: {e}")
        raise


def extract_info_from_pdf(pdf_path):
    """
    Lê o PDF e tenta extrair o número da demanda e o título com base em padrões resilientes.

    Parameters:
        pdf_path (Path): Path object to the PDF file.

    Returns:
        tuple: (numero, titulo) strings, or (None, None) if extraction fails.
    """
    print(f"{get_current_time()} 🔹 [STEP] [extract_info_from_pdf] Starting analysis on: {pdf_path.name}")
    try:
        raw_text = extract_text_from_pdf(pdf_path)
        text = normalize_pdf_text(raw_text)
        numero = find_number(text)
        titulo = find_title(text, numero) if numero else None
        
        print(f"{get_current_time()} ✅ [SUCCESS] [extract_info_from_pdf] Completed extraction for {pdf_path.name}. Numero: {numero}, Titulo: {titulo}")
        return numero, titulo
    except Exception as e:
        print(f"{get_current_time()} 🔴 [ERROR] [extract_info_from_pdf] Erro ao processar o arquivo {pdf_path.name}: {e}")
        print(f"{get_current_time()} ℹ️ [LOG] [extract_info_from_pdf] How to fix: Ensure the file is a valid, readable PDF document.")
        return None, None


def sanitize_filename(filename):
    """
    Remove caracteres inválidos para nomes de arquivos no sistema operacional.

    Parameters:
        filename (str): The base filename string.

    Returns:
        str: A clean, sanitized string suitable for file naming.
    """
    print(f"{get_current_time()} 🔹 [STEP] [sanitize_filename] Starting with filename: '{filename}'")
    clean = re.sub(r'[\\/*?:"<>|\n\r]', "", filename)
    clean = re.sub(r"\s+", " ", clean).strip().rstrip(".")
    
    # Limita o tamanho do título para evitar erros do sistema operacional (WinError 123)
    if len(clean) > 130:
        clean = clean[:130].strip()
        
    result = clean or "SEM_TITULO"
    print(f"{get_current_time()} ✅ [SUCCESS] [sanitize_filename] Completed. Final name: '{result}'")
    return result


def unique_path(path):
    """
    Evita colisões também em sistemas com comparação de nomes sem distinção de caixa.

    Parameters:
        path (Path): The desired file Path object.

    Returns:
        Path: A path guaranteed to not exist yet.
    """
    print(f"{get_current_time()} 🔹 [STEP] [unique_path] Starting check for path: {path.name}")
    if not path.exists():
        print(f"{get_current_time()} ✅ [SUCCESS] [unique_path] Completed. Path is unique.")
        return path
    for suffix in range(2, 10000):
        candidate = path.with_name(f"{path.stem} ({suffix}){path.suffix}")
        if not candidate.exists():
            print(f"{get_current_time()} ✅ [SUCCESS] [unique_path] Completed. Found unique suffix: {suffix}")
            return candidate
    print(f"{get_current_time()} 🔴 [ERROR] [unique_path] Não foi possível encontrar nome livre para '{path.name}'")
    raise OSError(f"Não foi possível encontrar nome livre para '{path.name}'")


def get_file_time(filepath):
    """
    Retrieves the file's creation time, falling back to modification time if necessary.
    
    Args:
        filepath (Path): The absolute path to the file.
        
    Returns:
        datetime: The parsed datetime object, or None if an error occurs.
    """
    print(f"{get_current_time()} 🔹 [STEP] [get_file_time] Starting extraction for: {filepath.name}")
    try:
        stat = os.stat(filepath)
    except OSError as e:
        print(f"{get_current_time()} 🔴 [ERROR] [get_file_time] OS Error getting file time for '{filepath.name}': {e}")
        return None
    except Exception as e:
        print(f"{get_current_time()} 🔴 [ERROR] [get_file_time] Unexpected error getting file time for '{filepath.name}': {e}")
        return None

    try:
        # Prioritize modification time over creation time
        result = datetime.fromtimestamp(stat.st_mtime)
        print(f"{get_current_time()} ✅ [SUCCESS] [get_file_time] Completed. Time: {result}")
        return result
    except AttributeError:
        result = datetime.fromtimestamp(stat.st_ctime)
        print(f"{get_current_time()} ✅ [SUCCESS] [get_file_time] Completed. Time: {result}")
        return result


def parse_date_prefix(filename):
    """
    Attempts to parse date/time prefix from the filename based on known formats.
    
    Args:
        filename (str): The name of the file to parse.
        
    Returns:
        tuple: (parsed_datetime, remaining_filename, matched_format_string)
               Returns (None, filename, None) if parsing fails.
    """
    print(f"{get_current_time()} 🔹 [STEP] [parse_date_prefix] Starting parsing for: '{filename}'")
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
                    print(f"{get_current_time()} ✅ [SUCCESS] [parse_date_prefix] Completed. Found: {dt}")
                    return dt, rest[3:], fmt
                elif rest.startswith('- ') or rest.startswith(' -'):
                    print(f"{get_current_time()} ✅ [SUCCESS] [parse_date_prefix] Completed. Found: {dt}")
                    return dt, rest[2:], fmt
                elif rest.startswith(' ') or rest.startswith('-') or rest.startswith('_'):
                    print(f"{get_current_time()} ✅ [SUCCESS] [parse_date_prefix] Completed. Found: {dt}")
                    return dt, rest[1:], fmt
                else:
                    print(f"{get_current_time()} ✅ [SUCCESS] [parse_date_prefix] Completed. Found: {dt}")
                    return dt, rest, fmt
            except ValueError:
                continue
    print(f"{get_current_time()} ℹ️ [LOG] [parse_date_prefix] No date prefix found.")
    return None, filename, None


def process_and_rename_pdf(filepath):
    """
    Processa e renomeia um único PDF, retornando True se houve sucesso.

    Parameters:
        filepath (Path): The original file Path object.

    Returns:
        bool: True if renamed successfully, False otherwise (ignored or failed).
    """
    print(f"{get_current_time()} 🔹 [STEP] [process_and_rename_pdf] Starting processing for: {filepath.name}")
    
    # Verifica se o arquivo já está no formato final esperado para evitar reprocessamento
    if re.match(r"^\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2} - \d+ - .+\.pdf$", filepath.name, re.IGNORECASE):
        print(f"{get_current_time()} ℹ️ [LOG] [process_and_rename_pdf] Arquivo '{filepath.name}' já está no formato esperado. Pulando extração.")
        return False

    numero, titulo = extract_info_from_pdf(filepath)
    
    if not (numero and titulo):
        print(f"{get_current_time()} 🔴 [ERROR] [process_and_rename_pdf] Não foi possível extrair número ou título completo de: {filepath.name}")
        return False
        
    sanitized_titulo = sanitize_filename(titulo)
    
    # Extrai a data do nome do arquivo (se presente) ou usa a data de modificação
    dt, _, fmt = parse_date_prefix(filepath.name)
    
    if dt:
        # Se o formato reconhecido não tem hora, pega dos metadados do arquivo
        if fmt and '%H' not in fmt:
            file_dt = get_file_time(filepath)
            if file_dt:
                dt = dt.replace(hour=file_dt.hour, minute=file_dt.minute, second=file_dt.second)
    else:
        dt = get_file_time(filepath)
        
    if dt:
        formatted_dt = dt.strftime("%Y.%m.%d-%H.%M")
        new_filename = f"{formatted_dt} - {numero} - {sanitized_titulo}.pdf".upper()
    else:
        new_filename = f"{numero} - {sanitized_titulo}.pdf".upper()
    
    if filepath.name.upper() == new_filename:
        print(f"{get_current_time()} ℹ️ [LOG] [process_and_rename_pdf] Arquivo '{filepath.name}' já possui o nome correto.")
        return False
        
    try:
        new_filepath = unique_path(filepath.with_name(new_filename))
        os.rename(filepath, new_filepath)
        print(f"{get_current_time()} ✅ [SUCCESS] [process_and_rename_pdf] Renomeado: '{filepath.name}' -> '{new_filepath.name}'")
        return True
    except Exception as e:
        print(f"{get_current_time()} 🔴 [ERROR] [process_and_rename_pdf] Falha ao renomear '{filepath.name}': {e}")
        print(f"{get_current_time()} ℹ️ [LOG] [process_and_rename_pdf] How to fix: Check file permissions and ensure the file is not open in another program.")
        return False


def main():
    """
    Main function to orchestrate the PDF scanning and renaming process.

    Returns:
        int: 0 on success or if no items to process, 1 if failures occurred.
    """
    print(f"{get_current_time()} 🔹 [STEP] [main] Starting process")
    current_dir = Path.cwd()
    print(f"{get_current_time()} ℹ️ [LOG] [main] Iniciando o mapeamento de PDFs no diretório corrente: {current_dir}")

    pdf_files = [f for f in sorted(current_dir.iterdir()) if f.suffix.lower() == ".pdf"]
    total_files = len(pdf_files)

    if total_files == 0:
        print(f"{get_current_time()} ℹ️ [LOG] [main] Nenhum arquivo PDF encontrado para processar no diretório.")
        return 0

    print(f"{get_current_time()} 🔹 [STEP] [main_cycle] Found {total_files} PDF files to process.")

    renamed_count = 0
    failures_or_ignored = 0
    error_reports = []

    for i, filepath in enumerate(pdf_files, 1):
        print(f"\n{get_current_time()} 🔹 [STEP] [main_cycle] Processing item {i} of {total_files}")
        print(f"{get_current_time()} ℹ️ [LOG] Processing: {filepath.name} with specific_parameters None")

        old_stdout = sys.stdout
        sys.stdout = capture_out = io.StringIO()
        
        try:
            success = process_and_rename_pdf(filepath)
        finally:
            sys.stdout = old_stdout
            
        output = capture_out.getvalue()
        print(output, end="")
        
        if success:
            print(f"{get_current_time()} ✅ [SUCCESS] [process_item] Successfully renamed {filepath.name}")
            renamed_count += 1
        else:
            print(f"{get_current_time()} 🔴 [ERROR/IGNORED] [process_item] File {filepath.name} was ignored or failed.")
            failures_or_ignored += 1
            if "🔴 [ERROR]" in output:
                error_reports.append((filepath.name, output))

    print(f"\n{get_current_time()} ✅ [SUCCESS] [main_cycle] Completed directory mapping.")

    summary = f"""
╔═══════════════════════════════════════════════╗
║          Processing Summary                   ║
╠═══════════════════════════════════════════════╣
║ Total Processed: {str(total_files).ljust(29)}║
║ Successes:       {str(renamed_count).ljust(29)}║
║ Ignored/Failed:  {str(failures_or_ignored).ljust(29)}║
╚═══════════════════════════════════════════════╝
"""
    print(summary)
    
    if error_reports:
        report_filename = current_dir / f"RENAME_ERROR_REPORT_{datetime.now().strftime('%Y.%m.%d-%H.%M')}.txt"
        try:
            with open(report_filename, "w", encoding="utf-8") as f:
                f.write("═"*80 + "\n")
                f.write(" " * 28 + "DETAILED ERROR REPORT\n")
                f.write("═"*80 + "\n")
                for fname, out in error_reports:
                    f.write(f"\n[FILE]: {fname}\n")
                    f.write("-" * 80 + "\n")
                    f.write(out.strip() + "\n")
                    f.write("-" * 80 + "\n")
                f.write("═"*80 + "\n")
            print(f"\n{get_current_time()} ℹ️ [LOG] Relatório de erros salvo em: {report_filename.name}")
        except Exception as e:
            print(f"\n{get_current_time()} 🔴 [ERROR] Falha ao salvar o relatório de erros: {e}")
        
    return 1 if error_reports else 0


if __name__ == "__main__":
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code)