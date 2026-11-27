import calendar
import os
import io
import logging
import re
import sys
import time
import unicodedata
import warnings
from pathlib import Path
from datetime import datetime
import importlib

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass



def print_error(message: str) -> None:
    """Prints an error message to stderr."""
    print(message, file=sys.stderr)


warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
logging.getLogger("pypdf").setLevel(logging.ERROR)

try:
    from pypdf import PdfReader
except ImportError as e:
    print(f"🔴 [ERROR] Required library 'pypdf' is not installed: {e}. Install with: pip install pypdf", file=sys.stderr)
    sys.exit(1)

try:
    import spacy
except ImportError:
    spacy = None

try:
    from langdetect import detect
except ImportError:
    detect = None


def log_error_line(message: str) -> None:
    """Prints an error line to stderr and also records it in stdout capture when active."""
    print(message, file=sys.stderr)
    if isinstance(sys.stdout, io.StringIO):
        print(message)


def _safe_rename(src, dst) -> None:
    """Renames a file with brief retries on transient Windows file locks."""
    last_err = None
    for attempt in range(1, 4):
        try:
            os.rename(src, dst)
            return
        except OSError as e:
            last_err = e
            if attempt < 3:
                time.sleep(0.4 * attempt)
    raise last_err


COLON_FIELD_MARKERS = (
    "Status",
    "Resolução",
    "Sistema de Origem",
    "Identificador de Origem",
    "Tipo",
    "Tipo da Demanda",
    "Solicitante",
    "Lotação Solicitante",
    "Equipe",
    "Acesso Restrito",
    "Prioridade",
    "Responsável",
    "Proprietário",
    "Criado Por",
    "Data de Criação",
    "Data da Solicitação",
    "Arquivado em",
    "Planejado para",
    "Severidade",
    "ID",
)

SECTION_MARKERS = (
    "Origem",
    "Detalhes",
    "Descrição",
    "Sistema e Contrato",
    "Previsibilidade de Atendimento",
    "Cronograma de Compromissos",
    "Discussão",
    "Visão Geral",
    "Faturamento",
    "ESG",
    "Links",
    "Histórico",
    "Informação de Faturamento",
    "Tags",
    "Tags Cliente",
    "Meio Ambiente, Social e Governança",
)

FIELD_MARKERS = (
    "Status", "Resolução", "Origem", "Detalhes", "Descrição", "Sistema e Contrato",
    "Previsibilidade de Atendimento", "Cronograma de Compromissos", "Discussão",
    "Visão Geral", "Faturamento", "ESG", "Links", "Histórico", "Informação de Faturamento"
)

_COLON_MARKERS_VARIANTS = tuple(dict.fromkeys(
    variant for m in COLON_FIELD_MARKERS for variant in (m, m.upper())
))
_SECTION_MARKERS_VARIANTS = tuple(dict.fromkeys(
    variant for m in SECTION_MARKERS for variant in (m, m.upper())
))

_COLON_LINE_RE = re.compile(
    r"^(?:" + "|".join(map(re.escape, _COLON_MARKERS_VARIANTS)) + r")\s*:"
)
_SECTION_LINE_RE = re.compile(
    r"^(?:" + "|".join(map(re.escape, _SECTION_MARKERS_VARIANTS)) + r")(?:\s*\([^)]*\))?\s*$"
)
_TAB_BAR_LINE_RE = re.compile(
    r"^(?:(?:" + "|".join(map(re.escape, _SECTION_MARKERS_VARIANTS)) + r")(?:\s+|$)){2,}$"
)
_PRINT_META_LINE_RE = re.compile(
    r"^(?:https?://|alm\.serpro/|\d{2}/\d{2}/\d{4},?\s+\d{2}:\d{2}\b)",
    re.IGNORECASE,
)
_STATUS_BOUNDARY_RE = re.compile(r"^(?:Status|STATUS)\s*:")
_INLINE_STATUS_RE = re.compile(r"\s+(?:Status|STATUS)\s*:")
_INLINE_COLON_MARKERS_RE = re.compile(
    r"\s+(?:" + "|".join(map(re.escape, _COLON_MARKERS_VARIANTS)) + r")\s*:"
)

# Global cache for loaded Spacy models
nlp_models_cache = {}


def get_current_time():
    """
    Returns the current timestamp in [HH:MM:SS] format.
    
    Returns:
        str: Current time formatted as [HH:MM:SS].
    """
    return f"[{datetime.now().strftime('%H:%M:%S')}]"


def _collapse_split_demand_number(text):
    """
    Reúne dígitos de números de demanda de 7 dígitos separados por espaços na extração do PDF.
    """
    def replacer(match):
        s = match.group(0)
        num_part = match.group(2)
        clean_num = re.sub(r"\s+", "", num_part)
        if len(clean_num) == 7:
            return match.group(1) + clean_num + match.group(3)
        return s

    return re.sub(
        r"(^|\bDemanda\s+|\bItem\s+de\s+Trabalho\s+)(\d[\d\s]{5,13}\d)(\s*:|\b)",
        replacer,
        text,
        flags=re.IGNORECASE,
    )


def normalize_pdf_lines(text):
    """
    Normaliza o texto do PDF preservando quebras de linha para identificar
    com precisão limites de campos e cabeçalhos de seção.

    Parameters:
        text (str): The raw text extracted from the PDF.

    Returns:
        list[str]: Non-empty normalized lines.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00ad", "").replace("\ufffd", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines = []
    for raw_line in text.split("\n"):
        line = re.sub(r"[\x00-\x1f\x7f]", " ", raw_line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            line = _collapse_split_demand_number(line)
            normalized_lines.append(line)
    return normalized_lines


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
    result = _collapse_split_demand_number(result)

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


def _is_field_boundary_line(line):
    """
    Retorna True se a linha representar o início de um campo ou seção do formulário
    ALM/EWM (e não uma continuação do título da demanda).
    """
    stripped = line.strip()
    if not stripped:
        return False
    if _COLON_LINE_RE.match(stripped):
        return True
    if _SECTION_LINE_RE.match(stripped):
        return True
    if _TAB_BAR_LINE_RE.match(stripped):
        return True
    if _PRINT_META_LINE_RE.match(stripped):
        return True
    return False


def _collect_title_from_line_match(lines, start_idx, first_part):
    """
    Coleta o título a partir de uma linha inicial até encontrar uma linha de fronteira
    (campo ou seção do formulário ALM/EWM).
    """
    parts = [first_part.strip()] if first_part and first_part.strip() else []
    boundary_line = None
    max_extra_lines = 6
    max_chars = 500

    for next_idx in range(start_idx + 1, min(len(lines), start_idx + 1 + max_extra_lines)):
        candidate_line = lines[next_idx]
        if _is_field_boundary_line(candidate_line):
            boundary_line = candidate_line
            break
        parts.append(candidate_line)
        if sum(len(p) for p in parts) > max_chars:
            break

    if not parts:
        return None

    joined = " ".join(parts)
    if boundary_line is None:
        m_inline = _INLINE_COLON_MARKERS_RE.search(joined)
        if m_inline:
            joined = joined[:m_inline.start()]
        elif len(parts) > 1:
            joined = parts[0]
    elif not _STATUS_BOUNDARY_RE.match(boundary_line):
        m_status = _INLINE_STATUS_RE.search(joined)
        if m_status:
            joined = joined[:m_status.start()]

    cleaned = clean_title(joined)
    return cleaned or None


def _find_title_from_lines(raw_text, number):
    """
    Busca o título preservando quebras de linha do PDF para evitar cortes em palavras
    comuns dentro do título (como 'status', 'resolução', 'origem', 'detalhes').
    """
    print(f"{get_current_time()} 🔹 [STEP] [_find_title_from_lines] Starting for number: {number}")
    lines = normalize_pdf_lines(raw_text)
    if not lines:
        return None

    header_re = re.compile(
        rf"(?:^|\s)(?i:(?:Demanda|Item\s+de\s+Trabalho)\s+)?{re.escape(number)}\s*:\s*(.*)$"
    )
    for idx, line in enumerate(lines):
        match = header_re.search(line)
        if match:
            result = _collect_title_from_line_match(lines, idx, match.group(1))
            if result:
                print(f"{get_current_time()} ✅ [SUCCESS] [_find_title_from_lines] Completed (header). Found: '{result}'")
                return result

    ewm_re = re.compile(r"(?:^|\s)(?i:Título)\s*:\s*\*?\s*(.*)$")
    for idx, line in enumerate(lines):
        match = ewm_re.search(line)
        if match:
            result = _collect_title_from_line_match(lines, idx, match.group(1))
            if result:
                print(f"{get_current_time()} ✅ [SUCCESS] [_find_title_from_lines] Completed (EWM). Found: '{result}'")
                return result

    print(f"{get_current_time()} ℹ️ [LOG] [_find_title_from_lines] No match found.")
    return None


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
        rf"(?i:(?:Demanda|Item\s+de\s+Trabalho)\s+)?{re.escape(number)}\s*:\s*(.+?){marker_end}",
        text,
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
    match = re.search(rf"\b{re.escape(number)}\s*:\s*(.{{1,300}})", text)
    if match:
        colon_split = r"\s+(?:Status|STATUS|Resolução|RESOLUÇÃO|Sistema de Origem|Tipo|Solicitante)\s*:"
        section_split = r"\s+(?:Origem|Detalhes|Descrição|Sistema e Contrato|Visão Geral)\b"
        candidate = re.split(
            rf"(?:{colon_split}|{section_split})",
            match.group(1),
            maxsplit=1,
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
    match = re.search(r"(?i:Título)\s*:\s*\*?\s*(.+?)" + marker_end, text)
    if match:
        result = clean_title(match.group(1))
        print(f"{get_current_time()} ✅ [SUCCESS] [_find_title_by_ewm_format] Completed. Found: '{result}'")
        return result
    print(f"{get_current_time()} ℹ️ [LOG] [_find_title_by_ewm_format] No match found.")
    return None


def find_title(text, number, raw_text=None):
    """
    Procura o título tanto no cabeçalho com ':' quanto no campo Título.

    Parameters:
        text (str): The complete parsed text from the PDF.
        number (str): The identified demand number.
        raw_text (str, optional): Raw extracted PDF text with line breaks preserved.

    Returns:
        str or None: The title, if any strategy successfully extracts it.
    """
    print(f"{get_current_time()} 🔹 [STEP] [find_title] Starting execution for number: {number}")
    source_for_lines = raw_text if raw_text is not None else (text if "\n" in text else None)
    if source_for_lines is not None:
        line_result = _find_title_from_lines(source_for_lines, number)
        if line_result:
            print(f"{get_current_time()} ✅ [SUCCESS] [find_title] Completed. Found title: '{line_result}'")
            return line_result

    colon_markers_group = "(?:" + "|".join(map(re.escape, _COLON_MARKERS_VARIANTS)) + r")\s*:"
    section_markers_group = "(?:" + "|".join(map(re.escape, _SECTION_MARKERS_VARIANTS)) + r")\b"
    marker_end = rf"(?=\s+(?:{colon_markers_group}|{section_markers_group})|$)"
    result = (
        _find_title_by_header(text, number, marker_end) or
        _find_title_by_id_only(text, number) or
        _find_title_by_ewm_format(text, marker_end)
    )
    if result:
        print(f"{get_current_time()} ✅ [SUCCESS] [find_title] Completed. Found title: '{result}'")
    else:
        print(f"{get_current_time()} ℹ️ [LOG] [find_title] No title pattern matched.")
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
        print(f"{get_current_time()} ℹ️ [LOG] [find_number] No demand number pattern matched.")
    return result


def extract_text_from_pdf(pdf_path):
    """
    Lê o conteúdo do PDF, limitado às primeiras 3 páginas.
    """
    print(f"{get_current_time()} 🔹 [STEP] [extract_text_from_pdf] Starting reading: {pdf_path.name}")
    try:
        reader = PdfReader(pdf_path)
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception:
                pass
        pages_text = []
        for idx, page in enumerate(reader.pages[:3]):
            try:
                extracted = page.extract_text()
                if extracted:
                    pages_text.append(extracted)
            except Exception as page_err:
                log_error_line(f"{get_current_time()} 🔴 [ERROR] [extract_text_from_pdf] Failed page {idx + 1} of {pdf_path.name}: {page_err}")
        result = "\n".join(pages_text)
        print(f"{get_current_time()} ✅ [SUCCESS] [extract_text_from_pdf] Completed text extraction.")
        return result
    except Exception as e:
        log_error_line(f"{get_current_time()} 🔴 [ERROR] [extract_text_from_pdf] Failed to read PDF {pdf_path.name}: {e}")
        raise


def is_demanda_pdf(text):
    """
    Verifica se o texto do PDF possui indícios fortes de ser um documento de demanda.
    
    Parameters:
        text (str): Texto extraído do PDF.
        
    Returns:
        bool: True se parecer uma demanda, False caso contrário.
    """
    print(f"{get_current_time()} 🔹 [STEP] [is_demanda_pdf] Checking if PDF is a demand.")
    if not text:
        return False
        
    text_lower = text.lower()
    
    strong_terms = [
        "gestão de demandas",
        "gestao de demandas",
        "demandas (siged)",
        "ibm engineering workflow management"
    ]
    
    if any(term in text_lower for term in strong_terms):
        print(f"{get_current_time()} ✅ [SUCCESS] [is_demanda_pdf] Strong term found. It is a demand.")
        return True
        
    has_demanda = "demanda" in text_lower
    has_tipo_demanda = "tipo: demanda" in text_lower or "tipo:demanda" in text_lower
    
    form_fields = ["detalhes", "origem", "status:", "solicitante:", "título:"]
    found_fields = sum(1 for field in form_fields if field in text_lower)
    
    if has_tipo_demanda or (has_demanda and found_fields >= 2):
        print(f"{get_current_time()} ✅ [SUCCESS] [is_demanda_pdf] Conjunction of terms found. It is a demand.")
        return True
        
    print(f"{get_current_time()} ℹ️ [LOG] [is_demanda_pdf] Not identified as a demand.")
    return False


def extract_info_from_pdf(pdf_path):
    """
    Lê o PDF e tenta extrair o número da demanda e o título com base em padrões resilientes.

    Parameters:
        pdf_path (Path): Path object to the PDF file.

    Returns:
        tuple: (numero, titulo, text) strings, or (None, None, "") if extraction fails.
    """
    print(f"{get_current_time()} 🔹 [STEP] [extract_info_from_pdf] Starting analysis on: {pdf_path.name}")
    try:
        raw_text = extract_text_from_pdf(pdf_path)
        text = normalize_pdf_text(raw_text)
        numero = find_number(text)
        titulo = find_title(text, numero, raw_text=raw_text) if numero else None
        
        print(f"{get_current_time()} ✅ [SUCCESS] [extract_info_from_pdf] Completed extraction for {pdf_path.name}. Numero: {numero}, Titulo: {titulo}")
        return numero, titulo, text
    except Exception as e:
        log_error_line(f"{get_current_time()} 🔴 [ERROR] [extract_info_from_pdf] Erro ao processar o arquivo {pdf_path.name}: {e}")
        log_error_line(f"{get_current_time()} 🔴 [ERROR] [extract_info_from_pdf] How to fix: Ensure the file is a valid, readable PDF document.")
        return None, None, ""


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
    if len(clean) > 255:
        clean = clean[:255].strip()
        
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
    log_error_line(f"{get_current_time()} 🔴 [ERROR] [unique_path] Não foi possível encontrar nome livre para '{path.name}'")
    raise OSError(f"Não foi possível encontrar nome livre para '{path.name}'")


def get_file_time(filepath):
    """
    Retrieves the file's modification time, falling back safely if timestamps are invalid.
    """
    print(f"{get_current_time()} 🔹 [STEP] [get_file_time] Starting extraction for: {filepath.name}")
    try:
        stat = os.stat(filepath)
    except OSError as e:
        log_error_line(f"{get_current_time()} 🔴 [ERROR] [get_file_time] OS Error getting file time for '{filepath.name}': {e}")
        return None
    except Exception as e:
        log_error_line(f"{get_current_time()} 🔴 [ERROR] [get_file_time] Unexpected error getting file time for '{filepath.name}': {e}")
        return None

    for ts_attr in ("st_mtime", "st_ctime"):
        ts = getattr(stat, ts_attr, None)
        if ts is not None:
            try:
                result = datetime.fromtimestamp(ts)
                print(f"{get_current_time()} ✅ [SUCCESS] [get_file_time] Completed. Time: {result}")
                return result
            except (OSError, OverflowError, ValueError):
                continue

    result = datetime.now()
    print(f"{get_current_time()} ✅ [SUCCESS] [get_file_time] Completed with current time fallback: {result}")
    return result


def _extract_rest_if_valid_boundary(filename, length, fmt):
    """
    Verifies that filename[:length] ends on a valid separator or extension boundary
    and returns the remaining filename with any leading separator stripped.
    """
    rest = filename[length:]
    if not rest:
        return "" if fmt != "%Y" else None

    _, ext = os.path.splitext(filename)
    has_real_ext = bool(ext and re.match(r"^\.[A-Za-z0-9]{1,10}$", ext) and not ext[1:].isdigit())

    for separator, sep_len in ((' - ', 3), ('- ', 2), (' -', 2), (' ', 1), ('-', 1), ('_', 1)):
        if rest.startswith(separator):
            if fmt == "%Y":
                if separator == ' ':
                    return None
                after = rest[sep_len:]
                if not after or (has_real_ext and after == ext):
                    return None
            return rest[sep_len:]

    if has_real_ext and rest == ext and fmt != "%Y":
        return rest

    if length >= 8 and fmt != "%Y" and rest[0].isalpha():
        return rest

    return None


def needs_datetime_completion(fmt):
    """Returns True if any date/time component (month, day, hour, minute, second) is missing from fmt."""
    if not fmt:
        return True
    has_month = any(tok in fmt for tok in ("%m", "%B", "%b"))
    has_hour = any(tok in fmt for tok in ("%H", "%I"))
    return not (has_month and "%d" in fmt and has_hour and "%M" in fmt and "%S" in fmt)


def complete_datetime_from_file(dt, fmt, file_dt):
    """
    Completes only the missing date/time components in `dt` (according to `fmt`)
    using the file's modification timestamp `file_dt`.
    """
    if not fmt:
        return file_dt

    year = dt.year
    has_month = any(tok in fmt for tok in ("%m", "%B", "%b"))
    month = dt.month if has_month else file_dt.month

    if "%d" in fmt:
        day = dt.day
    else:
        max_day = calendar.monthrange(year, month)[1]
        day = min(file_dt.day, max_day)

    has_hour = any(tok in fmt for tok in ("%H", "%I"))
    hour = dt.hour if has_hour else file_dt.hour
    minute = dt.minute if "%M" in fmt else file_dt.minute
    second = dt.second if "%S" in fmt else file_dt.second

    return datetime(year, month, day, hour, minute, second)


def parse_date_prefix(filename):
    """
    Attempts to parse date/time prefix from the filename based on known full and partial formats.
    
    Args:
        filename (str): The name of the file to parse.
        
    Returns:
        tuple: (parsed_datetime, remaining_filename, matched_format_string)
               Returns (None, filename, None) if parsing fails.
    """
    print(f"{get_current_time()} 🔹 [STEP] [parse_date_prefix] Starting parsing for: '{filename}'")
    english_months = (
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    )
    english_patterns = (
        (r"^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\s+(\d{2})-(\d{2})-(\d{2})", "%B %d %Y %H-%M-%S"),
        (r"^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\s+(\d{2})-(\d{2})", "%B %d %Y %H-%M"),
        (r"^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", "%B %d %Y"),
        (r"^([A-Za-z]+)\s+(\d{4})", "%B %Y"),
    )
    for pat, eng_fmt in english_patterns:
        m = re.match(pat, filename, re.IGNORECASE)
        if not m:
            continue
        month_name = m.group(1).casefold()
        if month_name not in english_months:
            continue
        month = english_months.index(month_name) + 1
        rest_candidate = _extract_rest_if_valid_boundary(filename, m.end(), eng_fmt)
        if rest_candidate is None:
            continue
        try:
            if eng_fmt == "%B %d %Y %H-%M-%S":
                day, year, hour, minute, second = map(int, m.groups()[1:])
                dt = datetime(year, month, day, hour, minute, second)
            elif eng_fmt == "%B %d %Y %H-%M":
                day, year, hour, minute = map(int, m.groups()[1:])
                dt = datetime(year, month, day, hour, minute)
            elif eng_fmt == "%B %d %Y":
                day, year = map(int, m.groups()[1:])
                dt = datetime(year, month, day)
            else:
                year = int(m.group(2))
                dt = datetime(year, month, 1)
            if 1900 <= dt.year <= 2100:
                print(f"{get_current_time()} ✅ [SUCCESS] [parse_date_prefix] Completed. Found: {dt}")
                return dt, rest_candidate, eng_fmt
        except ValueError:
            continue

    formats = [
        "%Y.%m.%d-%H.%M.%S", "%Y.%m.%d_%H.%M.%S", "%Y.%m.%d %H.%M.%S",
        "%Y-%m-%d-%H-%M-%S", "%Y-%m-%d_%H-%M-%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H-%M-%S",
        "%Y-%m-%d-%H.%M.%S", "%Y-%m-%d_%H.%M.%S", "%Y-%m-%d %H.%M.%S",
        "%d.%m.%Y-%H.%M.%S", "%d-%m-%Y-%H.%M.%S", "%d-%m-%Y_%H-%M.%S",
        "%Y%m%d_%H%M%S", "%Y%m%d-%H%M%S", "%y%m%d_%H%M%S", "%y%m%d-%H%M%S", "%Y%m%d%H%M%S",
        "%Y.%m.%d-%H.%M", "%Y.%m.%d_%H.%M", "%Y.%m.%d %H.%M",
        "%Y-%m-%d-%H-%M", "%Y-%m-%d_%H-%M", "%Y-%m-%d %H-%M",
        "%Y-%m-%d-%H.%M", "%Y-%m-%d_%H.%M", "%Y-%m-%d %H.%M",
        "%d.%m.%Y-%H.%M", "%d-%m-%Y-%H.%M", "%d-%m-%Y_%H.%M",
        "%Y%m%d_%H%M", "%Y%m%d-%H%M", "%y%m%d_%H%M", "%y%m%d-%H%M", "%Y%m%d%H%M",
        "%Y.%m.%d-%H", "%Y.%m.%d_%H",
        "%Y-%m-%d-%H", "%Y-%m-%d_%H",
        "%d.%m.%Y-%H", "%d-%m-%Y-%H",
        "%Y%m%d_%H", "%Y%m%d-%H",
        "%Y.%m.%d", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d",
        "%Y.%m", "%Y-%m", "%m.%Y", "%m-%Y",
        "%Y",
    ]
    
    for length in range(25, 3, -1):
        if length > len(filename):
            continue
        prefix = filename[:length]
        for fmt in formats:
            if fmt == "%Y" and not (length == 4 and prefix.isdigit()):
                continue
            try:
                dt = datetime.strptime(prefix, fmt)
                if not (1900 <= dt.year <= 2100):
                    continue
                if any(c in fmt for c in ("%Y%m", "%y%m", "%m%d", "%H%M", "%M%S")) and dt.strftime(fmt) != prefix:
                    continue
                rest_candidate = _extract_rest_if_valid_boundary(filename, length, fmt)
                if rest_candidate is not None:
                    print(f"{get_current_time()} ✅ [SUCCESS] [parse_date_prefix] Completed. Found: {dt}")
                    return dt, rest_candidate, fmt
            except ValueError:
                continue
    print(f"{get_current_time()} ℹ️ [LOG] [parse_date_prefix] No date prefix found.")
    return None, filename, None


def generate_new_filename(filename, filepath):
    """
    Generates the targeted standard filename using parsed or file system dates.
    """
    print(f"{get_current_time()} 🔹 [STEP] [generate_new_filename] Starting for: '{filename}'")
    prefix_match = re.match(r"^(\[ .*? \] - )(.*)$", filename)
    if prefix_match:
        existing_prefix = prefix_match.group(1)
        name_to_parse = prefix_match.group(2)
    else:
        existing_prefix = ""
        name_to_parse = filename

    dt, rest_of_name, fmt = parse_date_prefix(name_to_parse)
    target_fmt = "%Y.%m.%d-%H.%M.%S"
    suffix = filepath.suffix
    has_real_ext = bool(suffix and re.match(r"^\.[A-Za-z0-9]{1,10}$", suffix) and not suffix[1:].isdigit())

    if dt:
        formatted_existing = dt.strftime(target_fmt)
        if fmt == target_fmt and (
            name_to_parse.startswith(formatted_existing + " - ")
            or (has_real_ext and name_to_parse == formatted_existing + suffix)
            or name_to_parse == formatted_existing
        ):
            print(f"{get_current_time()} ✅ [SUCCESS] [generate_new_filename] Already perfectly formatted.")
            return None, "Already perfectly formatted with date prefix"
            
        if needs_datetime_completion(fmt):
            file_dt = get_file_time(filepath)
            if not file_dt:
                log_error_line(f"{get_current_time()} 🔴 [ERROR] [generate_new_filename] Cannot process without a valid date.")
                return None, "Cannot process without a valid date in file metadata"
            dt = complete_datetime_from_file(dt, fmt, file_dt)
    else:
        dt = get_file_time(filepath)
        if not dt:
            log_error_line(f"{get_current_time()} 🔴 [ERROR] [generate_new_filename] Cannot process without a valid date.")
            return None, "Cannot process without a valid date in file metadata"
            
        rest_of_name = name_to_parse
        
        if rest_of_name.startswith(' - '):
            rest_of_name = rest_of_name[3:]
        elif rest_of_name.startswith('- ') or rest_of_name.startswith(' -'):
            rest_of_name = rest_of_name[2:]

    formatted_dt = dt.strftime(target_fmt)
    
    if dt and ((has_real_ext and rest_of_name == suffix) or rest_of_name == ""):
        new_name = f"{existing_prefix}{formatted_dt}{rest_of_name}"
    else:
        prefix = f"{existing_prefix}{formatted_dt} - "
        if suffix and rest_of_name.endswith(suffix):
            rest_of_name_stem = rest_of_name[:-len(suffix)]
        else:
            rest_of_name_stem = rest_of_name
            
        max_allowed = min(255, 258 - len(str(filepath.parent)))
        available_for_stem = max_allowed - len(prefix) - len(suffix)
        if available_for_stem < 10:
            available_for_stem = 10
            
        if len(rest_of_name_stem) > available_for_stem:
            rest_of_name_stem = rest_of_name_stem[:available_for_stem].strip().rstrip(".")
            
        new_name = f"{prefix}{rest_of_name_stem}{suffix}"
    
    if new_name == filename:
        print(f"{get_current_time()} ✅ [SUCCESS] [generate_new_filename] Already perfectly formatted.")
        return None, "Already perfectly formatted with date prefix"
        
    print(f"{get_current_time()} ✅ [SUCCESS] [generate_new_filename] Generated new name: '{new_name}'")
    return new_name, None


def process_and_rename_by_time(filepath):
    """
    Handles the date extraction and renaming operation for a file.
    """
    print(f"{get_current_time()} 🔹 [STEP] [process_and_rename_by_time] Starting for: {filepath.name}")
    
    new_name, skip_reason = generate_new_filename(filepath.name, filepath)
    if not new_name:
        print(f"{get_current_time()} ℹ️ [LOG] [process_and_rename_by_time] Skipping '{filepath.name}': {skip_reason}")
        return "IGNORED"
        
    try:
        if filepath.name.lower() == new_name.lower():
            if filepath.name != new_name:
                temp_path = filepath.with_name(new_name + ".tmp")
                _safe_rename(filepath, temp_path)
                _safe_rename(temp_path, filepath.with_name(new_name))
                print(f"{get_current_time()} ✅ [SUCCESS] [process_and_rename_by_time] Renamed (case adjustment): '{filepath.name}' -> '{new_name}'")
                return "SUCCESS"
            return "IGNORED"
            
        new_filepath = unique_path(filepath.with_name(new_name))
        _safe_rename(filepath, new_filepath)
        print(f"{get_current_time()} ✅ [SUCCESS] [process_and_rename_by_time] Renamed: '{filepath.name}' -> '{new_filepath.name}'")
        return "SUCCESS"
    except Exception as e:
        log_error_line(f"{get_current_time()} 🔴 [ERROR] [process_and_rename_by_time] Falha ao renomear '{filepath.name}': {e}")
        return "ERROR"


def load_spacy_model(lang_code):
    """
    Loads spacy and the appropriate NLP model based on language.
    Falls back to other installed models or None (rule-based fallback) if unavailable.
    """
    func_name = "load_spacy_model"
    print(f"{get_current_time()} 🔹 [STEP] [{func_name}] Starting - Parameters: lang_code={lang_code}")
    if spacy is None:
        print(f"{get_current_time()} ℹ️ [LOG] [{func_name}] Spacy not available; using rule-based fallback.")
        return None

    spacy_models_map = {
        "pt": "pt_core_news_sm",
        "en": "en_core_web_sm",
        "es": "es_core_news_sm",
        "it": "it_core_news_sm",
        "de": "de_core_news_sm",
        "fr": "fr_core_news_sm",
        "nl": "nl_core_news_sm",
        "el": "el_core_news_sm",
        "ru": "ru_core_news_sm",
        "xx": "xx_ent_wiki_sm"
    }
    primary = spacy_models_map.get(lang_code, "xx_ent_wiki_sm")
    candidates = [primary] + [m for m in ("xx_ent_wiki_sm", "pt_core_news_sm", "en_core_web_sm") if m != primary]

    for model_name in candidates:
        if model_name in nlp_models_cache:
            print(f"{get_current_time()} ✅ [SUCCESS] [{func_name}] Found in cache: {model_name}")
            return nlp_models_cache[model_name]
        try:
            try:
                model_module = importlib.import_module(model_name)
                model = model_module.load()
            except (ImportError, AttributeError):
                model = spacy.load(model_name)
            nlp_models_cache[model_name] = model
            print(f"{get_current_time()} ✅ [SUCCESS] [{func_name}] Loaded: {model_name}")
            return model
        except Exception:
            continue

    print(f"{get_current_time()} ℹ️ [LOG] [{func_name}] No Spacy model could be loaded for '{lang_code}'; using rule-based fallback.")
    return None


def abbreviate_words(text, nlp_model, target_pos, preserve_first=True, protect_first_n=100):
    """
    Abbreviates words in text matching specific POS tags.
    """
    func_name = "abbreviate_words"
    print(f"{get_current_time()} 🔹 [STEP] [{func_name}] Starting - Parameters: target_pos={target_pos}, preserve_first={preserve_first}")
    try:
        print(f"{get_current_time()} 🔹 [STEP] [{func_name}] Abbreviating words based on POS tags.")
        if not text or text.upper() == "EMPTY":
            print(f"{get_current_time()} ✅ [SUCCESS] [{func_name}] Empty text, nothing to abbreviate.")
            return ""

        if nlp_model is None:
            words = text.split()
            pos = 0
            out_words = []
            for idx, word in enumerate(words):
                has_alpha = any(c.isalpha() for c in word)
                if pos >= protect_first_n and has_alpha and len(word) > 4 and not (preserve_first and idx == 0):
                    out_words.append(word[:3] + ".")
                else:
                    out_words.append(word)
                pos += len(word) + 1
            return " ".join(out_words).strip()

        doc = nlp_model(text)
        out = ""
        first_alpha_seen = False

        for token in doc:
            word = token.text
            has_alpha = any(c.isalpha() for c in word)

            is_candidate = token.pos_ in target_pos and has_alpha and len(word) > 4

            if has_alpha and preserve_first and not first_alpha_seen:
                is_candidate = False
                first_alpha_seen = True

            if token.idx < protect_first_n:
                is_candidate = False

            if is_candidate:
                out += word[:3] + "." + token.whitespace_
            else:
                out += word + token.whitespace_

        res = out.strip()
        print(f"{get_current_time()} ✅ [SUCCESS] [{func_name}] Abbreviated result length: {len(res)}")
        return res
    except Exception as e:
        log_error_line(f"{get_current_time()} 🔴 [ERROR] [{func_name}] Failed to abbreviate words: {e}")
        return text


def apply_abbreviation_phases(summary, nlp_model):
    """
    Applies progressive abbreviation rules to the summary if it exceeds 255 chars.
    """
    func_name = "apply_abbreviation_phases"
    print(f"{get_current_time()} 🔹 [STEP] [{func_name}] Starting - Parameters: summary evaluation")
    if len(summary) <= 255:
        print(f"{get_current_time()} ✅ [SUCCESS] [{func_name}] Summary is within limit, no abbreviation needed.")
        return summary

    print(f"{get_current_time()} 🔹 [STEP] [{func_name}] Summary > 255 chars. Applying NLP abbreviation phases.")

    # Phase 1: Abbreviate Adverbs (ADV)
    adv_pos = ["ADV"]
    summary = abbreviate_words(summary, nlp_model, adv_pos)
    if len(summary) <= 255:
        print(f"{get_current_time()} ✅ [SUCCESS] [{func_name}] Completed at Phase 1.")
        return summary

    # Phase 2: Abbreviate Adjectives and Verbs (ADJ, VERB)
    adj_verb_pos = ["ADJ", "VERB"]
    summary = abbreviate_words(summary, nlp_model, adj_verb_pos)
    if len(summary) <= 255:
        print(f"{get_current_time()} ✅ [SUCCESS] [{func_name}] Completed at Phase 2.")
        return summary

    # Phase 3: Abbreviate Nouns and Proper Nouns (NOUN, PROPN)
    noun_pos = ["NOUN", "PROPN"]
    summary = abbreviate_words(summary, nlp_model, noun_pos)
    if len(summary) <= 255:
        print(f"{get_current_time()} ✅ [SUCCESS] [{func_name}] Completed at Phase 3.")
        return summary

    # Phase 4: Abbreviate all
    all_pos = ["ADV", "ADJ", "VERB", "NOUN", "PROPN"]
    summary = abbreviate_words(summary, nlp_model, all_pos)

    if len(summary) > 255:
        if nlp_model is not None:
            doc = nlp_model(summary)
            truncated = ""
            for token in doc:
                if len(truncated) + len(token.text) + 3 > 255:
                    break
                truncated += token.text + token.whitespace_
            summary = truncated.strip() + "..."
        else:
            summary = summary[:252].rstrip() + "..."

    print(f"{get_current_time()} ✅ [SUCCESS] [{func_name}] Completed NLP abbreviation phases (all phases).")
    return summary


def is_all_uppercase_title(title: str) -> bool:
    """
    Retorna True se o título estiver inteiramente em letras maiúsculas.
    """
    return sum(c.isalpha() for c in title) > 4 and title.isupper()


def prettify_name_logic(name: str, nlp_model) -> str:
    """
    Applies the prettification logic to a filename string.
    """
    func_name = "prettify_name_logic"
    print(f"{get_current_time()} 🔹 [STEP] [{func_name}] Starting - Applying prettify name logic")
    
    # 1. CamelCase splitting: add space between lowercase/number and uppercase
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', name)
    # Add space between uppercase and uppercase followed by lowercase (e.g., XMLParser -> XML Parser)
    name = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', name)
    
    # 2. Replace underscores with spaces while preserving hyphens
    name = name.replace('_', ' ')
    name = " ".join(name.split())
    
    if not name:
        return name

    was_all_upper = name.isupper()

    if nlp_model is None:
        minor_words = {"a", "o", "as", "os", "e", "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
                       "por", "para", "com", "sem", "um", "uma", "the", "of", "and", "in", "on", "to", "for", "at", "by"}
        words = name.split()
        formatted = []
        for idx, w in enumerate(words):
            core = re.sub(r"^[^A-Za-zÀ-ÖØ-öø-ÿ]+|[^A-Za-zÀ-ÖØ-öø-ÿ]+$", "", w)
            if not was_all_upper and 2 <= len(core) <= 4 and core.isupper():
                formatted.append(w)
            elif idx == 0 or core.lower() not in minor_words:
                formatted.append(re.sub(r"[A-Za-zÀ-ÖØ-öø-ÿ]", lambda m: m.group(0).upper(), w.lower(), count=1))
            else:
                formatted.append(w.lower())
        result = " ".join(formatted).strip()
        if result:
            result = result[0].upper() + result[1:]
        print(f"{get_current_time()} ✅ [SUCCESS] [{func_name}] Completed prettify name logic (rule-based fallback)")
        return result

    original_text = name
    text_for_nlp = name.lower() if was_all_upper else name
        
    doc = nlp_model(text_for_nlp)
    
    result = ""
    for token in doc:
        word = token.text
        original_word = original_text[token.idx : token.idx + len(word)]
        has_alpha = any(c.isalpha() for c in word)

        if has_alpha:
            if not was_all_upper and 2 <= len(word) <= 4 and original_word.isupper():
                word_fmt = original_word
            elif was_all_upper and token.pos_ == "PROPN" and 2 <= len(word) <= 4 and original_word.isupper():
                word_fmt = original_word
            elif token.pos_ in ["NOUN", "PROPN", "VERB", "AUX", "ADJ", "ADV"]:
                word_fmt = word.capitalize()
            else:
                word_fmt = word.lower()
        else:
            word_fmt = word.lower()

        result += word_fmt + token.whitespace_
        
    result = result.strip()
    
    if result:
        # 4. The first letter of the full filename must be capitalized.
        result = result[0].upper() + result[1:]
        
    print(f"{get_current_time()} ✅ [SUCCESS] [{func_name}] Completed prettify name logic")
    return result


def process_file(filepath):
    """
    Processa um arquivo, sendo ele PDF (extraindo demanda) ou outro formato (apenas data).
    """
    print(f"{get_current_time()} 🔹 [STEP] [process_file] Starting processing for: {filepath.name}")
    
    if filepath.suffix.lower() != ".pdf":
        print(f"{get_current_time()} ℹ️ [LOG] [process_file] O arquivo '{filepath.name}' não é PDF. Aplicando lógica de data-hora.")
        return process_and_rename_by_time(filepath)
        
    # Processamento de PDF
    if re.match(r"^(?:\[ .*? \] - )?\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}(?: - |\.pdf$)", filepath.name, re.IGNORECASE):
        print(f"{get_current_time()} ℹ️ [LOG] [process_file] PDF '{filepath.name}' já começa com data e hora completas. Pulando extração.")
        return "IGNORED"

    if re.match(r"^(?:\[ .*? \] - )?\d{4}\.\d{2}\.\d{2}-\d{2}(?:\.\d{2})?(?: - |\.pdf$)", filepath.name, re.IGNORECASE):
        print(f"{get_current_time()} ℹ️ [LOG] [process_file] PDF '{filepath.name}' está com data/hora parcial. Mantendo nome atual e completando apenas o restante do horário.")
        return process_and_rename_by_time(filepath)

    _pref_match = re.match(r"^(?:\[ .*? \] - )?(.*)$", filepath.name)
    _dt_check, _rest_check, _ = parse_date_prefix(_pref_match.group(1) if _pref_match else filepath.name)
    if _dt_check and re.match(r"^\d{7} - .+\.pdf$", _rest_check, re.IGNORECASE):
        print(f"{get_current_time()} ℹ️ [LOG] [process_file] PDF '{filepath.name}' já possui demanda extraída e data parcial. Completando apenas o restante da data/hora.")
        return process_and_rename_by_time(filepath)

    numero, titulo, text = extract_info_from_pdf(filepath)
    
    if not (numero and titulo):
        if not is_demanda_pdf(text):
            print(f"{get_current_time()} ℹ️ [LOG] [process_file] O PDF '{filepath.name}' não é uma demanda. Será renomeado com data-hora.")
            return process_and_rename_by_time(filepath)

        log_error_line(f"{get_current_time()} 🔴 [ERROR] [process_file] Não foi possível extrair número ou título completo de: {filepath.name}")
        return "ERROR"
        
    needs_prettify = is_all_uppercase_title(titulo)
    needs_abbreviation = len(titulo) > 255
    current_nlp = None

    if needs_prettify or needs_abbreviation:
        try:
            lang_code = detect(titulo) if detect is not None else "xx"
        except Exception:
            lang_code = "xx"
        current_nlp = load_spacy_model(lang_code)

    if needs_prettify:
        titulo = prettify_name_logic(titulo, current_nlp)
        # Capitalize contents within square brackets after Title Case conversion
        titulo = re.sub(r'\[(.*?)\]', lambda m: f"[{m.group(1).upper()}]", titulo)

    if needs_abbreviation or len(titulo) > 255:
        titulo = apply_abbreviation_phases(titulo, current_nlp)

    sanitized_titulo = sanitize_filename(titulo)
    
    _pref_match2 = re.match(r"^(\[ .*? \] - )(.*)$", filepath.name)
    _existing_pref2 = _pref_match2.group(1) if _pref_match2 else ""
    _name_for_dt = _pref_match2.group(2) if _pref_match2 else filepath.name
    dt, _, fmt = parse_date_prefix(_name_for_dt)
    
    if dt:
        if needs_datetime_completion(fmt):
            file_dt = get_file_time(filepath)
            if file_dt:
                dt = complete_datetime_from_file(dt, fmt, file_dt)
    else:
        dt = get_file_time(filepath)
        
    if dt:
        formatted_dt = dt.strftime("%Y.%m.%d-%H.%M.%S")
        prefix = f"{_existing_pref2}{formatted_dt} - {numero} - "
    else:
        prefix = f"{_existing_pref2}{numero} - "
        
    suffix = ".pdf"
    max_allowed = min(255, 258 - len(str(filepath.parent)))
    available_for_title = max_allowed - len(prefix) - len(suffix)
    
    if available_for_title < 10:
        available_for_title = 10
        
    if len(sanitized_titulo) > available_for_title:
        sanitized_titulo = sanitized_titulo[:available_for_title].strip().rstrip(".")
        
    new_filename = f"{prefix}{sanitized_titulo}{suffix}"
    
    if filepath.name.lower() == new_filename.lower():
        print(f"{get_current_time()} ℹ️ [LOG] [process_file] Arquivo '{filepath.name}' já possui o nome base correto.")
        if filepath.name != new_filename:
            try:
                temp_path = filepath.with_name(new_filename + ".tmp")
                _safe_rename(filepath, temp_path)
                _safe_rename(temp_path, filepath.with_name(new_filename))
                print(f"{get_current_time()} ✅ [SUCCESS] [process_file] Renomeado (ajuste de caixa): '{filepath.name}' -> '{new_filename}'")
                return "SUCCESS"
            except Exception as e:
                log_error_line(f"{get_current_time()} 🔴 [ERROR] [process_file] Falha ao ajustar caixa de '{filepath.name}': {e}")
                return "ERROR"
        return "IGNORED"
        
    try:
        new_filepath = unique_path(filepath.with_name(new_filename))
        _safe_rename(filepath, new_filepath)
        print(f"{get_current_time()} ✅ [SUCCESS] [process_file] Renomeado: '{filepath.name}' -> '{new_filepath.name}'")
        return "SUCCESS"
    except Exception as e:
        log_error_line(f"{get_current_time()} 🔴 [ERROR] [process_file] Falha ao renomear '{filepath.name}': {e}")
        log_error_line(f"{get_current_time()} 🔴 [ERROR] [process_file] How to fix: Check file permissions.")
        return "ERROR"


def filter_eligible_files(directory):
    """
    Filtra os arquivos elegíveis no diretório.
    """
    eligible = []
    self_name = os.path.basename(__file__)
    self_bat = os.path.splitext(self_name)[0] + ".bat"
    try:
        entries = sorted(directory.iterdir())
    except OSError as e:
        log_error_line(f"{get_current_time()} 🔴 [ERROR] [filter_eligible_files] Erro ao listar diretório '{directory}': {e}")
        return [], False

    for f in entries:
        try:
            if not f.is_file():
                continue
        except OSError:
            continue
        filename = f.name
        if filename.startswith('!-') or filename.startswith('_') or filename in (self_name, self_bat) or filename.lower().endswith(('.py', '.url', '.lnk')):
            continue
        eligible.append(f)
    return eligible, True


def main():
    """
    Main function to orchestrate the scanning and renaming process.

    Returns:
        int: 0 on success or if no items to process, 1 if failures occurred.
    """
    print(f"{get_current_time()} 🔹 [STEP] [main] Starting process")
    current_dir = Path.cwd()
    print(f"{get_current_time()} ℹ️ [LOG] [main] Iniciando o mapeamento de arquivos no diretório corrente: {current_dir}")

    files_to_process, scan_ok = filter_eligible_files(current_dir)
    if not scan_ok:
        return 1
    total_files = len(files_to_process)

    if total_files == 0:
        print(f"{get_current_time()} ℹ️ [LOG] [main] Nenhum arquivo elegível encontrado para processar no diretório.")
        return 0

    print(f"{get_current_time()} 🔹 [STEP] [main_cycle] Found {total_files} files to process.")

    renamed_count = 0
    ignored_count = 0
    failed_count = 0
    error_reports = []

    for i, filepath in enumerate(files_to_process, 1):
        print(f"\n{get_current_time()} 🔹 [STEP] [main_cycle] Processing item {i} of {total_files}")
        print(f"{get_current_time()} ℹ️ [LOG] Processing: {filepath.name}")

        old_stdout = sys.stdout
        sys.stdout = capture_out = io.StringIO()
        
        try:
            status = process_file(filepath)
        except Exception as exc:
            log_error_line(f"{get_current_time()} 🔴 [ERROR] [process_file] Unexpected error processing '{filepath.name}': {exc}")
            status = "ERROR"
        finally:
            sys.stdout = old_stdout
            
        output = capture_out.getvalue()
        print(output, end="")
        
        if status == "SUCCESS":
            print(f"{get_current_time()} ✅ [SUCCESS] [process_item] Successfully renamed {filepath.name}")
            renamed_count += 1
        elif status == "IGNORED":
            print(f"{get_current_time()} ℹ️ [IGNORED] [process_item] File {filepath.name} was ignored.")
            ignored_count += 1
        else:
            log_error_line(f"{get_current_time()} 🔴 [ERROR] [process_item] File {filepath.name} failed.")
            failed_count += 1
            error_reports.append((filepath.name, output))

    print(f"\n{get_current_time()} ✅ [SUCCESS] [main_cycle] Completed directory mapping.")

    summary = f"""
╔═══════════════════════════════════════════════╗
║          Processing Summary                   ║
╠═══════════════════════════════════════════════╣
║ Total Processed: {str(total_files).ljust(29)}║
║ Successes:       {str(renamed_count).ljust(29)}║
║ Ignored:         {str(ignored_count).ljust(29)}║
║ Failed:          {str(failed_count).ljust(29)}║
╚═══════════════════════════════════════════════╝
"""
    print(summary)
    
    if error_reports:
        for fname, out in error_reports:
            log_filename = current_dir / Path(fname).with_suffix('.log').name
            try:
                with open(log_filename, "w", encoding="utf-8") as f:
                    f.write("═"*80 + "\n")
                    f.write(" " * 28 + "DETAILED ERROR REPORT\n")
                    f.write("═"*80 + "\n")
                    f.write(f"\n[FILE]: {fname}\n")
                    f.write("-" * 80 + "\n")
                    f.write(out.strip() + "\n")
                    f.write("-" * 80 + "\n")
                    f.write("═"*80 + "\n")
                print(f"\n{get_current_time()} ℹ️ [LOG] Relatório de erros salvo em: {log_filename.name}")
            except Exception as e:
                log_error_line(f"\n{get_current_time()} 🔴 [ERROR] Falha ao salvar o relatório de erros para {fname}: {e}")
        
    return 1 if failed_count > 0 else 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[*] Process interrupted by user.")
        sys.exit(0)
    except Exception as e:
        log_error_line(f"{get_current_time()} 🔴 [ERROR] [main] Fatal error: {e}")
        sys.exit(1)