import os
import io
import re
import sys
import unicodedata
from pathlib import Path
from pypdf import PdfReader
from datetime import datetime
import importlib
import spacy
from langdetect import detect


FIELD_MARKERS = (
    "Status", "Resolução", "Origem", "Detalhes", "Descrição", "Sistema e Contrato",
    "Previsibilidade de Atendimento", "Cronograma de Compromissos", "Discussão",
    "Visão Geral", "Faturamento", "ESG", "Links", "Histórico", "Informação de Faturamento"
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
        titulo = find_title(text, numero) if numero else None
        
        print(f"{get_current_time()} ✅ [SUCCESS] [extract_info_from_pdf] Completed extraction for {pdf_path.name}. Numero: {numero}, Titulo: {titulo}")
        return numero, titulo, text
    except Exception as e:
        print(f"{get_current_time()} 🔴 [ERROR] [extract_info_from_pdf] Erro ao processar o arquivo {pdf_path.name}: {e}")
        print(f"{get_current_time()} ℹ️ [LOG] [extract_info_from_pdf] How to fix: Ensure the file is a valid, readable PDF document.")
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


def generate_new_filename(filename, filepath):
    """
    Generates the targeted standard filename using parsed or file system dates.
    """
    print(f"{get_current_time()} 🔹 [STEP] [generate_new_filename] Starting for: '{filename}'")
    dt, rest_of_name, fmt = parse_date_prefix(filename)
    target_fmt = "%Y.%m.%d-%H.%M"

    if dt:
        if fmt == target_fmt and filename.startswith(dt.strftime(target_fmt) + " - "):
            print(f"{get_current_time()} ✅ [SUCCESS] [generate_new_filename] Already perfectly formatted.")
            return None, "Already perfectly formatted with date prefix"
            
        if fmt and '%H' not in fmt:
            file_dt = get_file_time(filepath)
            if file_dt:
                dt = dt.replace(hour=file_dt.hour, minute=file_dt.minute, second=file_dt.second)
    else:
        dt = get_file_time(filepath)
        if not dt:
            print(f"{get_current_time()} 🔴 [ERROR] [generate_new_filename] Cannot process without a valid date.")
            return None, "Cannot process without a valid date in file metadata"
            
        rest_of_name = filename
        
        if rest_of_name.startswith(' - '):
            rest_of_name = rest_of_name[3:]
        elif rest_of_name.startswith('- ') or rest_of_name.startswith(' -'):
            rest_of_name = rest_of_name[2:]

    formatted_dt = dt.strftime(target_fmt)
    
    prefix = f"{formatted_dt} - "
    suffix = filepath.suffix
    
    if rest_of_name.endswith(suffix):
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
        return True # Considered success (no action needed)
        
    try:
        if filepath.name.lower() == new_name.lower():
            if filepath.name != new_name:
                temp_path = filepath.with_name(new_name + ".tmp")
                os.rename(filepath, temp_path)
                os.rename(temp_path, filepath.with_name(new_name))
                print(f"{get_current_time()} ✅ [SUCCESS] [process_and_rename_by_time] Renamed (case adjustment): '{filepath.name}' -> '{new_name}'")
            return True
            
        new_filepath = unique_path(filepath.with_name(new_name))
        os.rename(filepath, new_filepath)
        print(f"{get_current_time()} ✅ [SUCCESS] [process_and_rename_by_time] Renamed: '{filepath.name}' -> '{new_filepath.name}'")
        return True
    except Exception as e:
        print(f"{get_current_time()} 🔴 [ERROR] [process_and_rename_by_time] Falha ao renomear '{filepath.name}': {e}")
        return False


def load_spacy_model(lang_code):
    """
    Loads spacy and the appropriate NLP model based on language.
    """
    func_name = "load_spacy_model"
    print(f"{get_current_time()} 🔹 [STEP] [{func_name}] Starting - Parameters: lang_code={lang_code}")
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
    model_name = spacy_models_map.get(lang_code, "xx_ent_wiki_sm")

    try:
        print(f"{get_current_time()} 🔹 [STEP] [{func_name}] Loading Spacy model '{model_name}' for language '{lang_code}'")

        if model_name in nlp_models_cache:
            print(f"{get_current_time()} ✅ [SUCCESS] [{func_name}] Found in cache: {model_name}")
            return nlp_models_cache[model_name]

        try:
            model_module = importlib.import_module(model_name)
            model = model_module.load()
            nlp_models_cache[model_name] = model
            print(f"{get_current_time()} ✅ [SUCCESS] [{func_name}] Loaded dynamically: {model_name}")
            return model
        except (ImportError, AttributeError):
            model = spacy.load(model_name)
            nlp_models_cache[model_name] = model
            print(f"{get_current_time()} ✅ [SUCCESS] [{func_name}] Loaded via spacy.load: {model_name}")
            return model
    except Exception as e:
        print(f"{get_current_time()} 🔴 [ERROR] [{func_name}] Error: Spacy model '{model_name}' could not be loaded ({e}).")
        raise RuntimeError(f"Spacy model '{model_name}' not loaded: {e}")


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
        print(f"{get_current_time()} 🔴 [ERROR] [{func_name}] Failed to abbreviate words: {e}")
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
        doc = nlp_model(summary)
        truncated = ""
        for token in doc:
            if len(truncated) + len(token.text) + 3 > 255:
                break
            truncated += token.text + token.whitespace_
        summary = truncated.strip() + "..."

    print(f"{get_current_time()} ✅ [SUCCESS] [{func_name}] Completed NLP abbreviation phases (all phases).")
    return summary


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

    original_text = name
    text_for_nlp = name
    if text_for_nlp.isupper():
        text_for_nlp = text_for_nlp.lower()
        
    doc = nlp_model(text_for_nlp)
    
    result = ""
    for token in doc:
        word = token.text
        original_word = original_text[token.idx : token.idx + len(word)]
        has_alpha = any(c.isalpha() for c in word)

        if has_alpha:
            if token.pos_ == "PROPN" and len(word) <= 4 and original_word.isupper():
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
    if re.match(r"^\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2} - ", filepath.name, re.IGNORECASE):
        print(f"{get_current_time()} ℹ️ [LOG] [process_file] PDF '{filepath.name}' já começa com data e hora. Pulando extração.")
        return False

    numero, titulo, text = extract_info_from_pdf(filepath)
    
    if not (numero and titulo):
        if not is_demanda_pdf(text):
            print(f"{get_current_time()} ℹ️ [LOG] [process_file] O PDF '{filepath.name}' não é uma demanda. Será renomeado com data-hora.")
            return process_and_rename_by_time(filepath)

        print(f"{get_current_time()} 🔴 [ERROR] [process_file] Não foi possível extrair número ou título completo de: {filepath.name}")
        return False
        
    try:
        lang_code = detect(titulo)
    except Exception:
        lang_code = "xx"
        
    current_nlp = load_spacy_model(lang_code)
    
    titulo = prettify_name_logic(titulo, current_nlp)
    titulo = apply_abbreviation_phases(titulo, current_nlp)
    
    # Capitalize contents within square brackets
    titulo = re.sub(r'\[(.*?)\]', lambda m: f"[{m.group(1).upper()}]", titulo)
        
    sanitized_titulo = sanitize_filename(titulo)
    
    dt, _, fmt = parse_date_prefix(filepath.name)
    
    if dt:
        if fmt and '%H' not in fmt:
            file_dt = get_file_time(filepath)
            if file_dt:
                dt = dt.replace(hour=file_dt.hour, minute=file_dt.minute, second=file_dt.second)
    else:
        dt = get_file_time(filepath)
        
    if dt:
        formatted_dt = dt.strftime("%Y.%m.%d-%H.%M")
        prefix = f"{formatted_dt} - {numero} - "
    else:
        prefix = f"{numero} - "
        
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
                os.rename(filepath, temp_path)
                os.rename(temp_path, filepath.with_name(new_filename))
                print(f"{get_current_time()} ✅ [SUCCESS] [process_file] Renomeado (ajuste de caixa): '{filepath.name}' -> '{new_filename}'")
                return True
            except Exception as e:
                print(f"{get_current_time()} 🔴 [ERROR] [process_file] Falha ao ajustar caixa de '{filepath.name}': {e}")
                return False
        return False
        
    try:
        new_filepath = unique_path(filepath.with_name(new_filename))
        os.rename(filepath, new_filepath)
        print(f"{get_current_time()} ✅ [SUCCESS] [process_file] Renomeado: '{filepath.name}' -> '{new_filepath.name}'")
        return True
    except Exception as e:
        print(f"{get_current_time()} 🔴 [ERROR] [process_file] Falha ao renomear '{filepath.name}': {e}")
        print(f"{get_current_time()} ℹ️ [LOG] [process_file] How to fix: Check file permissions.")
        return False


def filter_eligible_files(directory):
    """
    Filtra os arquivos elegíveis no diretório.
    """
    eligible = []
    for f in sorted(directory.iterdir()):
        if not f.is_file():
            continue
        filename = f.name
        if filename.startswith('!-') or filename.startswith('_') or filename == os.path.basename(__file__) or filename.lower().endswith(('.py', '.url', '.lnk')):
            continue
        eligible.append(f)
    return eligible


def main():
    """
    Main function to orchestrate the scanning and renaming process.

    Returns:
        int: 0 on success or if no items to process, 1 if failures occurred.
    """
    print(f"{get_current_time()} 🔹 [STEP] [main] Starting process")
    current_dir = Path.cwd()
    print(f"{get_current_time()} ℹ️ [LOG] [main] Iniciando o mapeamento de arquivos no diretório corrente: {current_dir}")

    files_to_process = filter_eligible_files(current_dir)
    total_files = len(files_to_process)

    if total_files == 0:
        print(f"{get_current_time()} ℹ️ [LOG] [main] Nenhum arquivo elegível encontrado para processar no diretório.")
        return 0

    print(f"{get_current_time()} 🔹 [STEP] [main_cycle] Found {total_files} files to process.")

    renamed_count = 0
    failures_or_ignored = 0
    error_reports = []

    for i, filepath in enumerate(files_to_process, 1):
        print(f"\n{get_current_time()} 🔹 [STEP] [main_cycle] Processing item {i} of {total_files}")
        print(f"{get_current_time()} ℹ️ [LOG] Processing: {filepath.name}")

        old_stdout = sys.stdout
        sys.stdout = capture_out = io.StringIO()
        
        try:
            success = process_file(filepath)
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