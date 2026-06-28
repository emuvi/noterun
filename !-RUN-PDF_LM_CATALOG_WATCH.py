import os
import re
import glob
import time
import sys
import shutil
import difflib
import PyPDF2
import json
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from lmstd import LMStd, ChatResponse, ListModelsResponse
from langdetect import detect
import spacy
import importlib
import traceback

# Global cache for loaded Spacy models
nlp_models_cache: Dict[str, Any] = {}


def get_current_time() -> str:
    """Returns the current time formatted as HH:MM:SS."""
    return datetime.now().strftime('%H:%M:%S')


def log_message(message: str) -> None:
    """Logs a message to the console with a timestamp."""
    print(f"[{get_current_time()}] {message}")


def log_step(step_name: str, status: str = "STARTING") -> None:
    """Logs a specific step of a function."""
    print(f"  [>] {step_name}... [{status}]")


def log_step_success(step_name: str, message: str = "") -> None:
    """Logs the success of a specific step."""
    msg = f" - {message}" if message else ""
    print(f"  [✓] {step_name}... [SUCCESS]{msg}")


def log_step_error(step_name: str, error_msg: str) -> None:
    """Logs an error occurring in a specific step."""
    print(f"  [X] {step_name}... [ERROR: {error_msg}]")


def print_summary_box(title: str, total: int, successes: int, fails: int) -> None:
    """Prints a visual box containing the summary of a cycle or session."""
    box_width = 50
    print("\n" + "╔" + "═" * (box_width - 2) + "╗")
    print("║" + f"{title}".center(box_width - 2) + "║")
    print("╠" + "═" * (box_width - 2) + "╣")
    print("║" + f"Total Processed: {total}".ljust(box_width - 2) + "║")
    print("║" + f"Successes:       {successes}".ljust(box_width - 2) + "║")
    print("║" + f"Failures:        {fails}".ljust(box_width - 2) + "║")
    print("╚" + "═" * (box_width - 2) + "╝\n")


def load_spacy_model(lang_code: str) -> Any:
    """Loads spacy and the appropriate NLP model based on language."""
    spacy_models_map: Dict[str, str] = {
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
        log_step(f"Loading Spacy model for language '{lang_code}'")

        if model_name in nlp_models_cache:
            log_step_success(
                f"Loading Spacy model for language '{lang_code}'", f"Found in cache: {model_name}")
            return nlp_models_cache[model_name]

        try:
            model_module = importlib.import_module(model_name)
            model = model_module.load()
            nlp_models_cache[model_name] = model
            log_step_success(
                f"Loading Spacy model for language '{lang_code}'", f"Loaded dynamically: {model_name}")
            return model
        except (ImportError, AttributeError):
            model = spacy.load(model_name)
            nlp_models_cache[model_name] = model
            log_step_success(
                f"Loading Spacy model for language '{lang_code}'", f"Loaded via spacy.load: {model_name}")
            return model
    except Exception as e:
        log_step_error(
            f"Loading Spacy model for language '{lang_code}'", str(e))
        log_message(
            f"Erro: Modelo '{model_name}' do spacy não pode ser carregado ({e}). Por favor, execute '!-LIB-Install.py' primeiro.")
        raise RuntimeError(f"Spacy model '{model_name}' not loaded: {e}")


# Initialize the LM Studio client pointing to the local LM Studio server.
try:
    log_step("Initializing LM Studio client")
    client = LMStd(base_url=os.environ.get("LMSTD_HOST", "http://localhost:1234"),
                   api_token=os.environ.get("LMSTD_APIKEY"))
    log_step_success("Initializing LM Studio client")
except Exception as e:
    log_step_error("Initializing LM Studio client", str(e))
    client = None  # type: ignore

FIELD_PROMPTS: Dict[str, str] = {
    "Author": """TASK: Extract the MAIN AUTHOR of the provided document. The author MUST be the single main entity that created the document.

RULES:
1. Look for the primary creator, writer, or responsible entity of the text. This must be the single main entity responsible for the document's creation.
2. If it is a PERSON, provide their full name (e.g., "John Doe", "Maria Silva").
3. If there are MULTIPLE authors, provide ONLY the first or principal author. Ignore the rest.
4. If there is NO person listed, identify the INSTITUTION or ORGANIZATION that produced the document (e.g., "World Health Organization", "Ministério da Educação").
5. If using an institution's name and an acronym is widely known or provided in the text, use ONLY the acronym (e.g., "WHO", "MEC").
6. Do not include titles like "Dr.", "Prof.", "Author:", etc.
7. If absolutely no author or institution can be found, you MUST return the exact word: EMPTY""",

    "Series": """TASK: Extract the MACRO-GROUP, COLLECTION, SERIES, or PARENT CONTAINER to which this document belongs.

PRINCIPLE: 
Think of document hierarchy. If this individual document is a "Child", what is its "Parent"? Is it one part of a larger, named grouping of works? We are looking for ANY overarching collection that groups multiple independent documents together.

RULES:
1. Identify the name of the overarching group. Examples include:
   - Book series or franchises (e.g., "The Lord of the Rings", "Série Vaga-Lume")
   - Journals, magazines, or periodicals (e.g., "Nature", "Revista Brasileira de Direito")
   - Publisher collections or editorial lines (e.g., "Coleção Primeiros Passos", "Very Short Introductions")
   - Corporate, government, or academic report series (e.g., "Working Paper Series", "Technical Reports")
2. Extract ONLY the name of this macro-group.
3. Do NOT include the specific main title of the individual document itself.
4. Do NOT include the publisher's name unless it is intrinsically part of the collection's formal name.
5. If the document is completely standalone and does not indicate belonging to any broader named group, you MUST return the exact word: EMPTY""",

    "Volume": """TASK: Extract the VOLUME, ISSUE, SEQUENCE, or NUMBERING of the provided document.

PRINCIPLE:
If this document belongs to a larger macro-group or series (identified as: "the extracted series"), what is this document's specific position, number, or sequential identifier within that group? We are looking for the exact indicator that places this "Child" document in order within its "Parent" container. 

RULES:
1. Look for indicators of sequence, volume, or numbering. Examples include:
   - Volume numbers (e.g., "Volume 1", "Vol. 2")
   - Journal issues (e.g., "Issue 4", "Nº 12", "Fascículo 3")
   - Part or book numbers in a series (e.g., "Book 3", "Parte II")
2. The overarching series/macro-group is "the extracted series". Focus on finding the numbering that corresponds to this group.
3. Extract the numeric or alphanumeric identifier exactly as it represents the sequence.
4. Do NOT include dates or years unless they act as the primary issue identifier.
5. If there is no volume, issue, or sequence numbering evident in the document, you MUST return the exact word: EMPTY""",

    "Title": """TASK: Extract the MAIN TITLE of the provided document.

RULES:
1. The main title is the primary name of the book, article, report, or document.
2. Do NOT include the Subtitle.
3. Do NOT include the author's name.
4. Do NOT include the word "Title:" in your output.
5. If absolutely no title can be identified, you MUST return the exact word: EMPTY""",

    "Subtitle": """TASK: Extract the SUBTITLE of the provided document.

RULES:
1. The subtitle is the secondary, explanatory title that usually follows the main title, often separated by a colon (:), dash (-), or placed on a new line in smaller text.
2. Example: If the full title is "Deep Learning: A Comprehensive Guide", the main title is "Deep Learning" and the subtitle is "A Comprehensive Guide". You must extract ONLY "A Comprehensive Guide".
3. Do NOT include the word "Subtitle:" in your output.
4. If the document does not have a clear subtitle, you MUST return the exact word: EMPTY""",

    "Edition": """TASK: Extract the EDITION information of the provided document.

RULES:
1. Look for text indicating the version or iteration of the document, such as "1st Edition", "2ª Edição", "Revised Edition", "Edição Revista e Ampliada", "3rd ed.".
2. Extract only the specific edition phrase.
3. Do NOT include publication dates, volume numbers, or publisher names.
4. If there is no edition information evident in the document, you MUST return the exact word: EMPTY"""
}


def extract_pdf_text(file_path: str) -> str:
    """Extracts text content from a PDF file using PyPDF2."""
    text = ""
    try:
        log_step("Extracting PDF text")
        with open(file_path, 'rb') as pdf_file:
            reader = PyPDF2.PdfReader(pdf_file)
            total_pages = len(reader.pages)

            if total_pages > 99:
                mid_start = (total_pages // 2) - 16
                pages_to_extract = sorted(set(
                    list(range(33)) +
                    list(range(mid_start, mid_start + 33)) +
                    list(range(total_pages - 33, total_pages))
                ))
            else:
                pages_to_extract = list(range(total_pages))

            for page_num in pages_to_extract:
                page = reader.pages[page_num]
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        log_step_success("Extracting PDF text", f"Extracted {len(text)} chars")
    except Exception as e:
        log_step_error("Extracting PDF text", str(e))
        log_message(f"Error reading PDF {file_path}: {e}")
    return text.strip()


def query_model_single_call(pdf_text: str, fields: List[str], prompts: Dict[str, str]) -> Dict[str, str]:
    """Queries the local AI model to extract all specific fields at once in JSON format."""
    content: Optional[str] = None
    try:
        log_step("Querying AI model for fields")
        master_prompt = "You are a highly capable AI assistant specialized in extracting metadata from documents.\n"
        master_prompt += "Your task is to extract multiple specific fields from the document text provided below based on the rules.\n\n"
        master_prompt += "### FIELD RULES ###\n"
        for field in fields:
            master_prompt += f"--- {field.upper()} ---\n{prompts[field]}\n\n"

        master_prompt += """### OUTPUT FORMAT ###
You MUST respond with ONLY a valid JSON object. Do not wrap the JSON in markdown blocks (like ```json), just output the raw JSON object.
Do not include any conversational text, explanations, or formatting.
The JSON object must contain exactly the following keys:
"""
        for field in fields:
            master_prompt += f'- "{field}"\n'

        master_prompt += """
The value for each key must be the extracted string exactly as found in the text (unless formatting is instructed), or "EMPTY" if no value was found.

Example Response:
{
  "Author": "John Doe",
  "Series": "EMPTY",
  "Volume": "EMPTY",
  "Title": "The Great Book",
  "Subtitle": "A story of a book",
  "Edition": "2nd Edition"
}

### DOCUMENT TEXT ###
"""
        full_prompt = f"{master_prompt}\n{pdf_text}"

        if client is None:
            raise ConnectionError("LM Studio client is not initialized.")

        response: ChatResponse = client.chat(
            system_prompt="You are a helpful assistant specialized in extracting specific information from documents into JSON format. You only respond with raw, valid JSON.",
            input_data=full_prompt,
            temperature=0.0,
        )
        if "output" in response:
            for item in response.get("output", []):
                if item.get("type") == "message":
                    content = item.get("content")
                    break

        if not content:
            log_step_error("Querying AI model for fields",
                           "Empty response content")
            return {f: "EMPTY" for f in fields}

        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        extracted_data = json.loads(content)

        result = {}
        for field in fields:
            val = extracted_data.get(field, "EMPTY")
            if not isinstance(val, str):
                val = str(val)
            val = val.strip().replace('\n', ' ').replace('\r', '')
            val = val.strip('"').strip("'")
            result[field] = val if val else "EMPTY"

        log_step_success("Querying AI model for fields")
        return result

    except json.JSONDecodeError as e:
        log_step_error("Querying AI model for fields",
                       f"JSON Decode Error: {e}")
        log_message(
            f"Error decoding JSON from model response: {e}\nResponse was:\n{content}")
        return {f: "EMPTY" for f in fields}
    except Exception as e:
        log_step_error("Querying AI model for fields", f"API Error: {e}")
        log_message(f"Error calling Local LM Studio API: {e}")
        raise ConnectionError("API Error 500")


def format_author(text: str, nlp_model: Any) -> str:
    """Formats the author string using the pattern SOBRENOME, N."""
    try:
        log_step("Formatting author")
        if not text or text.upper() == "EMPTY":
            log_step_success("Formatting author", "Empty author")
            return ""
        text = text.strip()

        if " " not in text and text.isupper():
            log_step_success("Formatting author", "Acronym detected")
            return text

        parts = text.split()
        if len(parts) == 1:
            log_step_success("Formatting author", "Single word author")
            return text.upper()

        last_name = parts[-1].upper()
        initials: List[str] = []

        text_to_analyze = " ".join(parts[:-1])
        if text_to_analyze.isupper():
            text_to_analyze = text_to_analyze.lower()

        doc = nlp_model(text_to_analyze)

        for token in doc:
            clean_text = re.sub(r'[^a-zA-ZÀ-ÿ]', '', token.text)
            if clean_text and token.pos_ not in ["ADP", "CCONJ", "SCONJ", "DET", "PRON", "PART"]:
                initials.append(clean_text[0].upper() + ".")

        if initials:
            res = f"{last_name}, {' '.join(initials)}"
        else:
            res = last_name

        log_step_success("Formatting author", f"Result: {res}")
        return res
    except Exception as e:
        log_step_error("Formatting author", str(e))
        return text


def format_title_case_nlp(text: str, nlp_model: Any) -> str:
    """Capitalizes nouns, proper nouns, verbs, adjectives, and adverbs using NLP."""
    try:
        log_step("Formatting title case")
        if not text or text.upper() == "EMPTY":
            log_step_success("Formatting title case", "Empty text")
            return ""

        original_text = text

        if text.isupper():
            text = text.lower()

        doc = nlp_model(text)

        result = ""
        for token in doc:
            word = token.text
            original_word = original_text[token.idx:token.idx + len(word)]
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

        res = result.strip()
        log_step_success("Formatting title case")
        return res
    except Exception as e:
        log_step_error("Formatting title case", str(e))
        return text


def abbreviate_words(text: str, nlp_model: Any, target_pos: List[str], preserve_first: bool = True) -> str:
    """Abbreviates words in text matching specific POS tags."""
    try:
        log_step("Abbreviating words")
        if not text or text.upper() == "EMPTY":
            log_step_success("Abbreviating words", "Empty text")
            return ""

        doc = nlp_model(text)
        out = ""
        first_alpha_seen = False

        for token in doc:
            word = token.text
            has_alpha = any(c.isalpha() for c in word)

            is_candidate = token.pos_ in target_pos and has_alpha and len(
                word) > 2

            if has_alpha and preserve_first and not first_alpha_seen:
                is_candidate = False
                first_alpha_seen = True

            if is_candidate:
                out += word[0] + "." + token.whitespace_
            else:
                out += word + token.whitespace_

        res = out.strip()
        log_step_success("Abbreviating words")
        return res
    except Exception as e:
        log_step_error("Abbreviating words", str(e))
        return text


def assemble_filename(author: str, series: str, volume: str, title: str, subtitle: str, edition: str, nlp_model: Any) -> str:
    """Assembles the final filename string applying progressive abbreviation rules."""
    try:
        log_step("Assembling filename")

        def build_name(t_ser: str, t_vol: str, t_title: str, t_sub: str, t_ed: str) -> str:
            parts = []
            if author:
                parts.append(f"{author} ~")
            if t_ser:
                parts.append(f"{{ {t_ser} }}")
            if t_vol:
                parts.append(f"[ {t_vol} ]")

            main_part = ""
            if t_title:
                main_part += t_title
            if t_sub:
                main_part += f" - {t_sub}"

            if main_part:
                parts.append(main_part)
            if t_ed:
                parts.append(f"( {t_ed} )")

            return " ".join(parts).strip()

        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            log_step_success("Assembling filename", "No abbreviations needed")
            return name

        # Phase 1: Abbreviate Adverbs (ADV)
        adv_pos = ["ADV"]
        subtitle = abbreviate_words(subtitle, nlp_model, adv_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            log_step_success("Assembling filename", "Abbreviated phase 1")
            return name

        title = abbreviate_words(title, nlp_model, adv_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            log_step_success("Assembling filename", "Abbreviated phase 1")
            return name

        series = abbreviate_words(series, nlp_model, adv_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            log_step_success("Assembling filename", "Abbreviated phase 1")
            return name

        # Phase 2: Abbreviate Adjectives and Verbs (ADJ, VERB)
        adj_verb_pos = ["ADJ", "VERB"]
        subtitle = abbreviate_words(subtitle, nlp_model, adj_verb_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            log_step_success("Assembling filename", "Abbreviated phase 2")
            return name

        title = abbreviate_words(title, nlp_model, adj_verb_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            log_step_success("Assembling filename", "Abbreviated phase 2")
            return name

        series = abbreviate_words(series, nlp_model, adj_verb_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            log_step_success("Assembling filename", "Abbreviated phase 2")
            return name

        # Phase 3: Abbreviate Nouns and Proper Nouns (NOUN, PROPN)
        noun_pos = ["NOUN", "PROPN"]
        subtitle = abbreviate_words(subtitle, nlp_model, noun_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            log_step_success("Assembling filename", "Abbreviated phase 3")
            return name

        title = abbreviate_words(title, nlp_model, noun_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            log_step_success("Assembling filename", "Abbreviated phase 3")
            return name

        series = abbreviate_words(series, nlp_model, noun_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            log_step_success("Assembling filename", "Abbreviated phase 3")
            return name

        # Phase 4: Abbreviate other fields aggressively (Edition, Volume)
        all_pos = ["ADV", "ADJ", "VERB", "NOUN", "PROPN"]
        edition = abbreviate_words(edition, nlp_model, all_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            log_step_success("Assembling filename", "Abbreviated phase 4")
            return name

        volume = abbreviate_words(volume, nlp_model, all_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            log_step_success("Assembling filename", "Abbreviated phase 4")
            return name

        # Phase 5: Force truncate characters if still > 240
        if len(name) > 240:
            name = name[:240].strip()
        log_step_success("Assembling filename", "Forced truncation")
        return name
    except Exception as e:
        log_step_error("Assembling filename", str(e))
        return "Unknown_Filename_Error"


def should_process(file_name: str) -> bool:
    """Checks if the file meets the criteria to be processed."""
    try:
        log_step("Checking if file should be processed")
        if not file_name.startswith("RAND "):
            log_step_success("Checking if file should be processed",
                             "False: Does not start with RAND")
            return False
        if "(FAILED)" in file_name or "(UNREADABLE)" in file_name or "(ERROR)" in file_name:
            log_step_success("Checking if file should be processed",
                             "False: Already marked as failed/unreadable/error")
            return False
        log_step_success("Checking if file should be processed", "True")
        return True
    except Exception as e:
        log_step_error("Checking if file should be processed", str(e))
        return False


def remove_overlapping_phrases(current_text: str, previous_text: str) -> str:
    """Intelligently detects and removes overlapping multi-word phrases."""
    try:
        log_step("Removing overlapping phrases")
        if not current_text or not previous_text or current_text == "EMPTY" or previous_text == "EMPTY":
            log_step_success("Removing overlapping phrases", "Empty input")
            return current_text

        curr_words = re.findall(r'\b\w+\b', current_text)
        prev_words = [w.lower() for w in re.findall(r'\b\w+\b', previous_text)]

        if not curr_words or not prev_words:
            log_step_success("Removing overlapping phrases", "No words found")
            return current_text

        matcher = difflib.SequenceMatcher(
            None, [w.lower() for w in curr_words], prev_words)
        match = matcher.find_longest_match(
            0, len(curr_words), 0, len(prev_words))

        cleaned_text = current_text
        if match.size > 0:
            matched_words = curr_words[match.a: match.a + match.size]
            match_str_len = sum(len(w) for w in matched_words)
            is_significant = False

            if match_str_len >= 3:
                if match.size == len(prev_words):
                    is_significant = True
                elif match.size >= 2:
                    is_significant = True
                elif match.size == 1 and len(matched_words[0]) >= 5:
                    is_significant = True

            if is_significant:
                regex_pattern = r'[\s\-:.,]*'.join([re.escape(w)
                                                   for w in matched_words])
                cleaned_text = re.sub(
                    regex_pattern, "", cleaned_text, count=1, flags=re.IGNORECASE).strip()

        cleaned_text = re.sub(r'^[-\s:.,]+|[-\s:.,]+$',
                              '', cleaned_text).strip()

        if not cleaned_text:
            log_step_success("Removing overlapping phrases",
                             "Cleaned to empty")
            return "EMPTY"

        if cleaned_text != current_text:
            cleaned_text = remove_overlapping_phrases(
                cleaned_text, previous_text)

        log_step_success("Removing overlapping phrases")
        return cleaned_text
    except Exception as e:
        log_step_error("Removing overlapping phrases", str(e))
        return current_text


def clean_repetitive_fields(current_field: str, raw_result: str, extracted_data: Dict[str, str]) -> str:
    """Iterates through previously extracted fields to prevent repetitions in the current field."""
    try:
        log_step("Cleaning repetitive fields")
        if raw_result == "EMPTY":
            log_step_success("Cleaning repetitive fields", "Empty raw result")
            return raw_result

        cleaned_result = raw_result
        for prev_field, prev_value in extracted_data.items():
            if prev_field != "Author" and prev_value != "EMPTY":
                cleaned_result = remove_overlapping_phrases(
                    cleaned_result, prev_value)
                if cleaned_result == "EMPTY":
                    break

        log_step_success("Cleaning repetitive fields")
        return cleaned_result
    except Exception as e:
        log_step_error("Cleaning repetitive fields", str(e))
        return raw_result


def get_files_to_process(current_dir: str) -> List[str]:
    """Scans the directory for PDF files that need processing."""
    try:
        log_step("Scanning for PDF files")
        pdf_files = glob.glob(os.path.join(current_dir, "*.pdf"))
        files_to_process = [os.path.basename(
            f) for f in pdf_files if os.path.basename(f).startswith("RAND ")]
        files_to_process = sorted(
            [f for f in files_to_process if "(UNREADABLE)" not in f and "(FAILED)" not in f and "(ERROR)" not in f])
        log_step_success("Scanning for PDF files",
                         f"Found {len(files_to_process)} file(s)")
        return files_to_process
    except Exception as e:
        log_step_error("Scanning for PDF files", str(e))
        return []


def handle_unreadable_file(file: str, current_dir: str) -> None:
    """Renames an unreadable file to prevent looping and moves to '!-ERRORS'."""
    try:
        log_step(f"Handling unreadable file: {file}")
        base_name, ext = os.path.splitext(file)
        error_name = f"{base_name} (UNREADABLE){ext}"
        errors_dir = os.path.join(current_dir, "!-ERRORS")
        os.makedirs(errors_dir, exist_ok=True)

        shutil.move(os.path.join(current_dir, file),
                    os.path.join(errors_dir, error_name))
        log_message(
            f"[{file}] -> Renamed to {error_name} and moved to '!-ERRORS' to prevent looping.")
        for related_file in os.listdir(current_dir):
            if related_file != file and os.path.splitext(related_file)[0] == base_name:
                rel_ext = os.path.splitext(related_file)[1]
                try:
                    shutil.move(os.path.join(current_dir, related_file), os.path.join(
                        errors_dir, f"{base_name} (UNREADABLE){rel_ext}"))
                except Exception:
                    pass
        log_step_success(f"Handling unreadable file: {file}")
    except Exception as e:
        log_step_error(f"Handling unreadable file: {file}", str(e))


def handle_error_file(file: str, current_dir: str) -> None:
    """Renames a file that caused an error to prevent looping and moves to '!-ERRORS'."""
    try:
        log_step(f"Handling error file: {file}")
        base_name, ext = os.path.splitext(file)
        error_name = f"{base_name} (ERROR){ext}"
        errors_dir = os.path.join(current_dir, "!-ERRORS")
        os.makedirs(errors_dir, exist_ok=True)

        shutil.move(os.path.join(current_dir, file),
                    os.path.join(errors_dir, error_name))
        log_message(
            f"[{file}] -> Renamed to {error_name} and moved to '!-ERRORS' to prevent looping on this file.")
        for related_file in os.listdir(current_dir):
            if related_file != file and os.path.splitext(related_file)[0] == base_name:
                rel_ext = os.path.splitext(related_file)[1]
                try:
                    shutil.move(os.path.join(current_dir, related_file), os.path.join(
                        errors_dir, f"{base_name} (ERROR){rel_ext}"))
                except Exception:
                    pass
        log_step_success(f"Handling error file: {file}")
    except Exception as rename_e:
        log_step_error(f"Handling error file: {file}", str(rename_e))


def process_single_file(file: str, current_dir: str, fields: List[str], prompts: Dict[str, str]) -> bool:
    """Processes a single PDF file, extracting text, querying model, formatting fields and renaming. Returns True if successful."""
    try:
        log_message(f"[{file}] -> Starting processing...")
        if not should_process(file):
            return False

        log_message(f"[{file}] -> Extracting text...")
        text = extract_pdf_text(os.path.join(current_dir, file))

        if not text:
            log_message(
                f"[{file}] -> Failed: Could not extract text from the PDF.")
            handle_unreadable_file(file, current_dir)
            return False

        text = text[:4000]

        try:
            log_step("Detecting language")
            lang_code = detect(text)
            log_step_success("Detecting language",
                             f"Language detected: {lang_code}")
        except Exception as e:
            lang_code = "xx"
            log_step_error(
                "Detecting language", f"Could not detect language ({e}), defaulting to (xx)")

        current_nlp = load_spacy_model(lang_code)

        log_message(f"[{file}] -> Analyzing fields in a single call...")
        start_time = time.time()

        raw_extracted_data = query_model_single_call(text, fields, prompts)

        elapsed_time = time.time() - start_time
        log_message(f"[{file}] -> LLM call completed in {elapsed_time:.2f}s")

        extracted_data: Dict[str, str] = {}
        for field in fields:
            raw_result = raw_extracted_data.get(field, "EMPTY")
            cleaned_result = clean_repetitive_fields(
                field, raw_result, extracted_data)
            extracted_data[field] = cleaned_result
            print(f"  - {field}: {cleaned_result}")

        if extracted_data.get("Author", "EMPTY") == "EMPTY" and extracted_data.get("Series", "EMPTY") == "EMPTY" and extracted_data.get("Title", "EMPTY") == "EMPTY":
            log_message(
                f"[{file}] -> Skipped: No Author, Series, or Title found. Moving to !-ERRORS.")
            errors_dir = os.path.join(current_dir, "!-ERRORS")
            os.makedirs(errors_dir, exist_ok=True)
            try:
                shutil.move(os.path.join(current_dir, file),
                            os.path.join(errors_dir, file))
                base_name = os.path.splitext(file)[0]
                for related_file in os.listdir(current_dir):
                    if related_file != file and os.path.splitext(related_file)[0] == base_name:
                        try:
                            shutil.move(os.path.join(current_dir, related_file), os.path.join(
                                errors_dir, related_file))
                        except Exception:
                            pass
            except Exception as move_e:
                log_message(f"[{file}] -> Error moving to !-ERRORS: {move_e}")
            return False

        fmt_author = format_author(extracted_data["Author"], current_nlp)
        fmt_series = format_title_case_nlp(
            extracted_data["Series"], current_nlp)
        fmt_volume = format_title_case_nlp(
            extracted_data["Volume"], current_nlp)
        fmt_title = format_title_case_nlp(extracted_data["Title"], current_nlp)
        fmt_subtitle = format_title_case_nlp(
            extracted_data["Subtitle"], current_nlp)
        fmt_edition = format_title_case_nlp(
            extracted_data["Edition"], current_nlp)

        if not fmt_title:
            fmt_title = "No Title"

        new_base_name = assemble_filename(
            fmt_author, fmt_series, fmt_volume, fmt_title, fmt_subtitle, fmt_edition, current_nlp)

        new_base_name = re.sub(r'[\\/*?:"<>|]', "_", new_base_name)
        new_base_name = re.sub(r'_{2,}', "_", new_base_name)
        new_file_name = f"{new_base_name}.pdf"

        old_path = os.path.join(current_dir, file)
        target_dir = os.path.dirname(current_dir)
        new_path = os.path.join(target_dir, new_file_name)

        if os.path.exists(new_path) and old_path.lower() != new_path.lower():
            counter = 2
            while True:
                new_file_name = f"{new_base_name} ({counter}).pdf"
                new_path = os.path.join(target_dir, new_file_name)
                if not os.path.exists(new_path) or old_path.lower() == new_path.lower():
                    break
                counter += 1

        try:
            log_step("Renaming file")
            shutil.move(old_path, new_path)
            log_step_success("Renaming file", f"Renamed to: '{new_file_name}'")

            orig_base_name = os.path.splitext(file)[0]
            final_base_name = os.path.splitext(new_file_name)[0]

            for related_file in os.listdir(current_dir):
                if related_file == file:
                    continue
                rel_base, rel_ext = os.path.splitext(related_file)
                if rel_base == orig_base_name:
                    related_target = os.path.join(
                        target_dir, f"{final_base_name}{rel_ext}")
                    try:
                        log_step(f"Renaming related file: {related_file}")
                        shutil.move(os.path.join(
                            current_dir, related_file), related_target)
                        log_step_success(
                            f"Renaming related file: {related_file}", f"Renamed to {os.path.basename(related_target)}")
                    except Exception as e:
                        log_step_error(
                            f"Renaming related file: {related_file}", str(e))

            return True
        except Exception as e:
            log_step_error("Renaming file", str(e))
            time.sleep(2)
            return False

    except ConnectionError as ce:
        log_message(f"[{file}] -> API Error: {ce}. Skipping to next file.")
        return False
    except Exception as e:
        log_message(
            f"[{file}] -> Unexpected error during file processing: {e}")
        traceback.print_exc()
        handle_error_file(file, current_dir)
        return False


def main_loop() -> None:
    """The main infinite loop for monitoring and processing files."""
    fields = ["Author", "Series", "Volume", "Title", "Subtitle", "Edition"]
    prompts = FIELD_PROMPTS

    proceed = input(
        "Do you want to proceed with AI renaming all PDF files starting with 'RAND ' in a single LLM call? (yes/no): ").strip().lower()
    if proceed != 'yes':
        log_message("Operation canceled.")
        return

    log_message("Entering continuous monitoring mode. Press Ctrl+C to exit.")
    print("-" * 90)

    waiting = False
    total_processed_files = 0
    total_failed_files = 0

    while True:
        try:
            current_dir = os.getcwd()
            files_to_process = get_files_to_process(current_dir)

            if not files_to_process:
                if not waiting:
                    print(
                        f"\r[{get_current_time()}] ⏳ Waiting for new PDF files... (Checking every 5s)", end="", flush=True)
                    waiting = True
                time.sleep(5)
                continue

            if waiting:
                print()
                waiting = False

            try:
                log_step("Checking LM Studio connection")
                if client is None:
                    raise ConnectionError(
                        "LM Studio client is not initialized.")
                _models: ListModelsResponse = client.list_models()
                log_step_success("Checking LM Studio connection")
            except Exception as e:
                log_step_error("Checking LM Studio connection", str(e))
                log_message(
                    "Error: Could not connect to LM Studio server. Retrying in 10s...")
                time.sleep(10)
                continue

            processed_files = 0
            failed_files = 0
            total_files_in_cycle = len(files_to_process)

            for index, file in enumerate(files_to_process):
                try:
                    progress_percentage = (
                        (index + 1) / total_files_in_cycle) * 100
                    print(
                        f"\n[{get_current_time()}] [PROGRESS] Processing file {index + 1} of {total_files_in_cycle} ({progress_percentage:.1f}%)")

                    success = process_single_file(
                        file, current_dir, fields, prompts)

                    if success:
                        processed_files += 1
                        log_message(
                            f"[{file}] -> Success! Cycle total: {processed_files}")
                    else:
                        failed_files += 1
                        log_message(
                            f"[{file}] -> Failed! Cycle total: {failed_files}")
                except Exception as e:
                    log_step_error(f"Processing file {file}", str(e))
                    failed_files += 1

            if processed_files > 0 or failed_files > 0:
                total_processed_files += processed_files
                total_failed_files += failed_files
                print_summary_box(
                    title=f"Cycle Summary",
                    total=processed_files + failed_files,
                    successes=processed_files,
                    fails=failed_files
                )
                print_summary_box(
                    title=f"Overall Session Summary",
                    total=total_processed_files + total_failed_files,
                    successes=total_processed_files,
                    fails=total_failed_files
                )

            time.sleep(2)

        except Exception as e:
            log_message(f"Critical error in main execution loop: {e}")
            traceback.print_exc()
            time.sleep(10)


def main() -> None:
    try:
        main_loop()
    except KeyboardInterrupt:
        log_message("Process interrupted by user. Exiting.")
    except Exception as e:
        log_message(f"Fatal error: {e}")
        input("Press Enter to exit...")


if __name__ == "__main__":
    main()
