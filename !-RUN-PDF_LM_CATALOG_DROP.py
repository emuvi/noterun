import os
import sys
import re
import glob
import time
import difflib
import PyPDF2
import json
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
import spacy
from langdetect import detect
import importlib
import traceback

from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDragEnterEvent, QDropEvent

from lmstd import LMStd, ChatResponse, ListModelsResponse

# Initialize the LM Studio client pointing to the local LM Studio server.
try:
    client = LMStd(base_url=os.environ.get("LMSTD_HOST", "http://localhost:1234"),
                   api_token=os.environ.get("LMSTD_APIKEY"))
except Exception as e:
    print(f"🔴 [Error] Failed to initialize LMStd client: {e}")
    sys.exit(1)

def get_current_time() -> str:
    """Returns the current time formatted as HH:MM:SS."""
    try:
        return datetime.now().strftime('%H:%M:%S')
    except Exception as e:
        print(f"🔴 [Error] get_current_time failed: {e}")
        return "00:00:00"

def print_step(message: str) -> None:
    """Prints a step in a process."""
    try:
        print(f"[{get_current_time()}] 🔹 [STEP] {message}")
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] print_step failed: {e}")

def print_success(message: str) -> None:
    """Prints a successful step completion."""
    try:
        print(f"[{get_current_time()}] ✅ [SUCCESS] {message}")
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] print_success failed: {e}")

def print_error(message: str) -> None:
    """Prints an error message."""
    try:
        print(f"[{get_current_time()}] 🔴 [ERROR] {message}")
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] print_error failed: {e}")

def print_progress(current: int, total: int, prefix: str = '', suffix: str = '', decimals: int = 1, length: int = 50, fill: str = '█', printEnd: str = "\n") -> None:
    """Call in a loop to create terminal progress bar."""
    try:
        if total == 0:
            return
        percent = ("{0:." + str(decimals) + "f}").format(100 * (current / float(total)))
        filledLength = int(length * current // total)
        bar = fill * filledLength + '-' * (length - filledLength)
        print(f'[{get_current_time()}] 🔄 {prefix} |{bar}| {percent}% {suffix}', end=printEnd)
    except Exception as e:
        print_error(f"Failed to print progress: {e}")

def print_summary_box(title: str, total: int, success: int, fails: int) -> None:
    """Prints a visually clear box summarizing the cycle."""
    try:
        box_width = 50
        print("\n" + "╔" + "═" * (box_width - 2) + "╗")
        title_str = f" 📊 SUMMARY: {title} "
        print("║" + title_str.center(box_width - 2) + "║")
        print("╠" + "═" * (box_width - 2) + "╣")
        print("║" + f" Total Items Processed : {total:<21}".ljust(box_width - 2) + "║")
        print("║" + f" ✅ Successes          : {success:<21}".ljust(box_width - 2) + "║")
        print("║" + f" 🔴 Failures           : {fails:<21}".ljust(box_width - 2) + "║")
        print("╚" + "═" * (box_width - 2) + "╝\n")
    except Exception as e:
        print_error(f"Failed to print summary box: {e}")

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

# --- NLP Functions ---
nlp_models_cache: Dict[str, Any] = {}

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
        print_step(f"[Load Spacy Model] Loading Spacy model for language '{lang_code}'")
        if model_name in nlp_models_cache:
            print_success(f"[Load Spacy Model] Found in cache: {model_name}")
            return nlp_models_cache[model_name]
        try:
            model_module = importlib.import_module(model_name)
            model = model_module.load()
            nlp_models_cache[model_name] = model
            print_success(f"[Load Spacy Model] Loaded dynamically: {model_name}")
            return model
        except (ImportError, AttributeError):
            model = spacy.load(model_name)
            nlp_models_cache[model_name] = model
            print_success(f"[Load Spacy Model] Loaded via spacy.load: {model_name}")
            return model
    except Exception as e:
        print_error(f"[Load Spacy Model] Error: {e}")
        print_error(f"Error: Spacy model '{model_name}' could not be loaded ({e}).")
        raise RuntimeError(f"Spacy model '{model_name}' not loaded: {e}")

def abbreviate_words(text: str, nlp_model: Any, target_pos: List[str], preserve_first: bool = True) -> str:
    """Abbreviates words in text matching specific POS tags."""
    try:
        print_step("[Abbreviate Words] Abbreviating words based on POS tags.")
        if not text or text.upper() == "EMPTY":
            print_success("[Abbreviate Words] Empty text")
            return ""

        doc = nlp_model(text)
        out = ""
        first_alpha_seen = False

        for token in doc:
            word = token.text
            has_alpha = any(c.isalpha() for c in word)
            is_candidate = token.pos_ in target_pos and has_alpha and len(word) > 2
            if has_alpha and preserve_first and not first_alpha_seen:
                is_candidate = False
                first_alpha_seen = True
            if is_candidate:
                out += word[0] + "." + token.whitespace_
            else:
                out += word + token.whitespace_

        res = out.strip()
        print_success(f"[Abbreviate Words] Abbreviated result length: {len(res)}")
        return res
    except Exception as e:
        print_error(f"[Abbreviate Words] Failed to abbreviate words: {e}")
        return text

# --- Catalog Specific NLP ---

def format_author(text: str, nlp_model: Any) -> str:
    """Formats the author string using the pattern SOBRENOME, N."""
    try:
        print_step("Formatting author")
        if not text or text.upper() == "EMPTY":
            print_success("Formatting author: Empty author")
            return ""
        text = text.strip()

        if " " not in text and text.isupper():
            print_success("Formatting author: Acronym detected")
            return text

        parts = text.split()
        if len(parts) == 1:
            print_success("Formatting author: Single word author")
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
        
        print_success(f"Formatting author: Result: {res}")
        return res
    except Exception as e:
        print_error(f"Formatting author failed: {e}")
        return text

def format_title_case_nlp(text: str, nlp_model: Any) -> str:
    """Capitalizes nouns, proper nouns, verbs, adjectives, and adverbs using NLP."""
    try:
        print_step("Formatting title case")
        if not text or text.upper() == "EMPTY":
            print_success("Formatting title case: Empty text")
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
        print_success("Formatting title case completed")
        return res
    except Exception as e:
        print_error(f"Formatting title case failed: {e}")
        return text

def assemble_filename(author: str, series: str, volume: str, title: str, subtitle: str, edition: str, nlp_model: Any) -> str:
    """Assembles the final filename string applying progressive abbreviation rules."""
    try:
        print_step("Assembling filename")
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
            print_success("Assembling filename: No abbreviations needed")
            return name

        # Phase 1: Abbreviate Adverbs (ADV)
        adv_pos = ["ADV"]
        subtitle = abbreviate_words(subtitle, nlp_model, adv_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            print_success("Assembling filename: Abbreviated phase 1")
            return name
        title = abbreviate_words(title, nlp_model, adv_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            print_success("Assembling filename: Abbreviated phase 1")
            return name
        series = abbreviate_words(series, nlp_model, adv_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            print_success("Assembling filename: Abbreviated phase 1")
            return name

        # Phase 2: Abbreviate Adjectives and Verbs (ADJ, VERB)
        adj_verb_pos = ["ADJ", "VERB"]
        subtitle = abbreviate_words(subtitle, nlp_model, adj_verb_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            print_success("Assembling filename: Abbreviated phase 2")
            return name
        title = abbreviate_words(title, nlp_model, adj_verb_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            print_success("Assembling filename: Abbreviated phase 2")
            return name
        series = abbreviate_words(series, nlp_model, adj_verb_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            print_success("Assembling filename: Abbreviated phase 2")
            return name

        # Phase 3: Abbreviate Nouns and Proper Nouns (NOUN, PROPN)
        noun_pos = ["NOUN", "PROPN"]
        subtitle = abbreviate_words(subtitle, nlp_model, noun_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            print_success("Assembling filename: Abbreviated phase 3")
            return name
        title = abbreviate_words(title, nlp_model, noun_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            print_success("Assembling filename: Abbreviated phase 3")
            return name
        series = abbreviate_words(series, nlp_model, noun_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            print_success("Assembling filename: Abbreviated phase 3")
            return name

        # Phase 4: Abbreviate other fields aggressively (Edition, Volume)
        all_pos = ["ADV", "ADJ", "VERB", "NOUN", "PROPN"]
        edition = abbreviate_words(edition, nlp_model, all_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            print_success("Assembling filename: Abbreviated phase 4")
            return name
        volume = abbreviate_words(volume, nlp_model, all_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 240:
            print_success("Assembling filename: Abbreviated phase 4")
            return name

        # Phase 5: Force truncate characters if still > 240
        if len(name) > 240:
            name = name[:240].strip()
        print_success("Assembling filename: Forced truncation")
        return name
    except Exception as e:
        print_error(f"Assembling filename failed: {e}")
        return "Unknown_Filename_Error"

def remove_overlapping_phrases(current_text: str, previous_text: str) -> str:
    """Intelligently detects and removes overlapping multi-word phrases."""
    try:
        print_step("Removing overlapping phrases")
        if not current_text or not previous_text or current_text == "EMPTY" or previous_text == "EMPTY":
            print_success("Removing overlapping phrases: Empty input")
            return current_text

        curr_words = re.findall(r'\b\w+\b', current_text)
        prev_words = [w.lower() for w in re.findall(r'\b\w+\b', previous_text)]

        if not curr_words or not prev_words:
            print_success("Removing overlapping phrases: No words found")
            return current_text

        matcher = difflib.SequenceMatcher(None, [w.lower() for w in curr_words], prev_words)
        match = matcher.find_longest_match(0, len(curr_words), 0, len(prev_words))

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
                regex_pattern = r'[\s\-:.,]*'.join([re.escape(w) for w in matched_words])
                cleaned_text = re.sub(regex_pattern, "", cleaned_text, count=1, flags=re.IGNORECASE).strip()

        cleaned_text = re.sub(r'^[-\s:.,]+|[-\s:.,]+$', '', cleaned_text).strip()

        if not cleaned_text:
            print_success("Removing overlapping phrases: Cleaned to empty")
            return "EMPTY"

        if cleaned_text != current_text:
            cleaned_text = remove_overlapping_phrases(cleaned_text, previous_text)

        print_success("Removing overlapping phrases completed")
        return cleaned_text
    except Exception as e:
        print_error(f"Removing overlapping phrases failed: {e}")
        return current_text

def clean_repetitive_fields(current_field: str, raw_result: str, extracted_data: Dict[str, str]) -> str:
    """Iterates through previously extracted fields to prevent repetitions in the current field."""
    try:
        print_step("Cleaning repetitive fields")
        if raw_result == "EMPTY":
            print_success("Cleaning repetitive fields: Empty raw result")
            return raw_result

        cleaned_result = raw_result
        for prev_field, prev_value in extracted_data.items():
            if prev_field != "Author" and prev_value != "EMPTY":
                cleaned_result = remove_overlapping_phrases(cleaned_result, prev_value)
                if cleaned_result == "EMPTY":
                    break

        print_success("Cleaning repetitive fields completed")
        return cleaned_result
    except Exception as e:
        print_error(f"Cleaning repetitive fields failed: {e}")
        return raw_result

# --- File Operations ---

def get_pages_to_extract(total_pages: int) -> List[int]:
    """Determines which pages to extract from a PDF based on total pages."""
    print_step(f"Determining pages to extract for a PDF with {total_pages} total pages.")
    pages_to_extract: List[int] = []
    try:
        if total_pages > 99:
            print_step("PDF has > 99 pages. Selecting first 33, middle 33, and last 33.")
            mid_start = (total_pages // 2) - 16
            pages_to_extract = sorted(set(
                list(range(33)) +
                list(range(mid_start, mid_start + 33)) +
                list(range(total_pages - 33, total_pages))
            ))
        else:
            print_step("PDF has <= 99 pages. Selecting all pages.")
            pages_to_extract = list(range(total_pages))
        print_success(f"Successfully determined {len(pages_to_extract)} pages to extract.")
        return pages_to_extract
    except Exception as e:
        print_error(f"Error determining pages to extract: {e}")
        return []

def extract_text_from_pages(reader: PyPDF2.PdfReader, pages_to_extract: List[int]) -> str:
    """Extracts text from specified pages of a PDF reader object."""
    total = len(pages_to_extract)
    print_step(f"Starting extraction cycle for {total} selected pages.")
    text = ""
    success_count = 0
    fail_count = 0

    try:
        for idx, page_num in enumerate(pages_to_extract):
            print_step(f"Extracting text from page {page_num + 1} (Index: {idx+1}/{total})")
            try:
                page = reader.pages[page_num]
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
                success_count += 1
                print_success(f"Extracted page {page_num + 1}")
            except Exception as page_err:
                print_error(f"Error extracting text from page {page_num + 1}: {page_err}")
                fail_count += 1
            print_progress(idx + 1, total, prefix='Page Extraction Progress', suffix='Complete', length=30)
        print_success(f"Successfully finished text extraction loop. Total characters: {len(text)}")
        print_summary_box("Page Extraction Cycle", total, success_count, fail_count)
        return text.strip()
    except Exception as e:
        print_error(f"Critical error during text extraction loop: {e}")
        print_summary_box("Page Extraction Cycle (Interrupted)", total, success_count, fail_count)
        return ""

def extract_pdf_text(file_path: str) -> str:
    """Opens a PDF file and extracts text content from it."""
    print_step(f"Starting text extraction for PDF file: '{file_path}'")
    text = ""
    try:
        print_step(f"Opening file '{file_path}' in binary read mode.")
        with open(file_path, 'rb') as pdf_file:
            print_success("File opened successfully.")
            print_step("Initializing PyPDF2 PdfReader.")
            reader = PyPDF2.PdfReader(pdf_file)
            total_pages = len(reader.pages)
            print_success(f"PDF reader initialized successfully. Total pages found: {total_pages}.")
            print_step("Calling get_pages_to_extract.")
            pages_to_extract = get_pages_to_extract(total_pages)
            if not pages_to_extract:
                print_error("No pages to extract. Aborting extraction.")
                return ""
            print_step("Calling extract_text_from_pages.")
            text = extract_text_from_pages(reader, pages_to_extract)
            print_success("Text extraction completed.")
    except FileNotFoundError:
        print_error(f"File not found at '{file_path}'.")
    except PermissionError:
        print_error(f"Permission denied when accessing '{file_path}'.")
    except Exception as e:
        print_error(f"Unexpected error reading PDF '{file_path}': {e}")
    return text

def query_model_single_call(pdf_text: str, fields: List[str], prompts: Dict[str, str]) -> Dict[str, str]:
    """Queries the local AI model to extract all specific fields at once in JSON format."""
    content: Optional[str] = None
    try:
        print_step("Querying AI model for fields")
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
            print_error("Querying AI model for fields failed: Empty response content")
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
            
        print_success("Successfully queried AI model for fields")
        return result
        
    except json.JSONDecodeError as e:
        print_error(f"JSON Decode Error: {e}\nResponse was:\n{content}")
        return {f: "EMPTY" for f in fields}
    except Exception as e:
        print_error(f"Error calling Local LM Studio API: {e}")
        return {f: "EMPTY" for f in fields}

def get_unique_new_path(current_dir: str, new_base_name: str, original_path: str) -> Optional[str]:
    """Generates a unique file path by appending a counter if the file already exists."""
    print_step(f"Generating a unique new file path for base name '{new_base_name}'.")
    try:
        new_file_name = f"{new_base_name}.pdf"
        new_path = os.path.join(current_dir, new_file_name)

        print_step(f"Checking if path '{new_path}' already exists.")
        if os.path.exists(new_path) and original_path.lower() != new_path.lower():
            print_step("Path already exists. Finding a unique filename with a counter.")
            counter = 2
            while True:
                new_file_name = f"{new_base_name} ({counter}).pdf"
                new_path = os.path.join(current_dir, new_file_name)
                if not os.path.exists(new_path) or original_path.lower() == new_path.lower():
                    print_success(f"Found unique filename: '{new_file_name}'")
                    break
                counter += 1
        else:
            print_success(f"Path '{new_path}' is available.")
        return new_path
    except Exception as e:
        print_error(f"Error generating unique new path: {e}")
        return None

def rename_file(old_path: str, new_path: str) -> bool:
    """Renames a file from old_path to new_path."""
    print_step(f"Attempting to rename '{old_path}' to '{new_path}'.")
    try:
        os.rename(old_path, new_path)
        print_success(f"Successfully renamed file to '{os.path.basename(new_path)}'.")
        return True
    except FileNotFoundError:
        print_error(f"Original file '{old_path}' not found for renaming.")
        return False
    except PermissionError:
        print_error(f"Permission denied when renaming '{old_path}'.")
        return False
    except Exception as e:
        print_error(f"Error renaming file '{old_path}' to '{new_path}': {e}")
        return False

def rename_associated_files(current_dir: str, old_base_name: str, final_new_base_name: str, new_pdf_name: str) -> None:
    """Searches for and renames other files in the directory that share the same old base name."""
    print_step(f"Searching for associated files with base name '{old_base_name}' in '{current_dir}'.")
    success_count = 0
    fail_count = 0
    total = 0

    try:
        files_in_dir = os.listdir(current_dir)
        total = len(files_in_dir)
        print_success(f"Found {total} files in directory. Filtering associated files.")

        for idx, f in enumerate(files_in_dir):
            print_step(f"Checking file for association: {f}")
            f_path = os.path.join(current_dir, f)
            try:
                if not os.path.isfile(f_path):
                    continue
                f_base_name, f_ext = os.path.splitext(f)
                if f_base_name == old_base_name and f != new_pdf_name:
                    print_step(f"Found associated file: '{f}'")
                    new_f_name = f"{final_new_base_name}{f_ext}"
                    new_f_path = os.path.join(current_dir, new_f_name)

                    print_step(f"Checking if target path '{new_f_path}' exists.")
                    if os.path.exists(new_f_path):
                        print_error(f"Cannot rename '{f}' to '{new_f_name}' because target already exists.")
                        fail_count += 1
                        continue

                    print_step(f"Attempting to rename associated file '{f}' to '{new_f_name}'.")
                    if rename_file(f_path, new_f_path):
                        print_success(f"Renamed associated file '{f}' to '{new_f_name}'")
                        success_count += 1
                    else:
                        print_error(f"Failed to rename associated file '{f}'.")
                        fail_count += 1
            except Exception as file_err:
                print_error(f"Error processing potential associated file '{f}': {file_err}")
                fail_count += 1
            print_progress(idx + 1, total, prefix='Associated Files Progress', suffix='Complete', length=30)

        print_success("Completed scanning and renaming associated files.")
        if success_count > 0 or fail_count > 0:
            print_summary_box("Associated Files Renaming", success_count + fail_count, success_count, fail_count)

    except Exception as e:
        print_error(f"Error during associated files renaming process: {e}")

# --- GUI Components ---

class DropZone(QLabel):
    """A QLabel subclass that accepts PDF file drops."""
    def __init__(self) -> None:
        try:
            print_step("Initializing DropZone widget.")
            super().__init__()
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setText("Drag and Drop PDF File Here\n\n🔹 Action: Catalog Metadata\n(Extracts metadata and renames file)")
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
            print_success("DropZone widget initialized successfully.")
        except Exception as e:
            print_error(f"Error initializing DropZone: {e}")

    def dragEnterEvent(self, a0: Optional[QDragEnterEvent]) -> None:
        try:
            if a0 is None:
                return
            mime_data = a0.mimeData()
            if mime_data is not None and mime_data.hasUrls():
                urls = mime_data.urls()
                if urls and urls[0].toLocalFile().lower().endswith('.pdf'):
                    a0.accept()
                    return
            a0.ignore()
        except Exception as e:
            print_error(f"Error in dragEnterEvent: {e}")
            if a0 is not None:
                a0.ignore()

    def dropEvent(self, a0: Optional[QDropEvent]) -> None:
        try:
            print_step("Drop event triggered.")
            if a0 is None:
                print_error("Received None for dropEvent. Ignoring.")
                return
            mime_data = a0.mimeData()
            if mime_data is not None and mime_data.hasUrls():
                urls = mime_data.urls()
                if urls:
                    file_path = urls[0].toLocalFile()
                    if file_path.lower().endswith('.pdf'):
                        print_success(f"Valid PDF file dropped: {file_path}")
                        self.process_file(file_path)
                    else:
                        print_error(f"Dropped file is not a PDF: {file_path}")
        except Exception as e:
            print_error(f"Error in dropEvent: {e}")

    def process_file(self, file_path: str) -> None:
        print_step(f"=== Beginning processing cycle for dropped file: {file_path} ===")
        success_count = 0
        fail_count = 0
        total = 1

        try:
            print_step("Attempting to extract text from dropped PDF.")
            text = extract_pdf_text(file_path)

            if not text:
                print_error("Failed to extract text or PDF is empty. Processing aborted.")
                fail_count += 1
            else:
                print_success(f"Extracted {len(text)} characters of text.")
                print_step("Proceeding to generate catalog filename.")

                text_trunc = text[:4000]

                try:
                    print_step("Detecting language")
                    lang_code = detect(text_trunc)
                    print_success(f"Language detected: {lang_code}")
                except Exception as e:
                    lang_code = "xx"
                    print_error(f"Could not detect language ({e}), defaulting to (xx)")

                current_nlp = load_spacy_model(lang_code)

                fields = ["Author", "Series", "Volume", "Title", "Subtitle", "Edition"]
                prompts = FIELD_PROMPTS
                
                raw_extracted_data = query_model_single_call(text_trunc, fields, prompts)
                
                extracted_data: Dict[str, str] = {}
                for field in fields:
                    raw_result = raw_extracted_data.get(field, "EMPTY")
                    cleaned_result = clean_repetitive_fields(field, raw_result, extracted_data)
                    extracted_data[field] = cleaned_result
                    print_step(f"Extracted {field}: {cleaned_result}")

                fmt_author = format_author(extracted_data["Author"], current_nlp)
                fmt_series = format_title_case_nlp(extracted_data["Series"], current_nlp)
                fmt_volume = format_title_case_nlp(extracted_data["Volume"], current_nlp)
                fmt_title = format_title_case_nlp(extracted_data["Title"], current_nlp)
                fmt_subtitle = format_title_case_nlp(extracted_data["Subtitle"], current_nlp)
                fmt_edition = format_title_case_nlp(extracted_data["Edition"], current_nlp)

                if not fmt_title:
                    fmt_title = "No Title"

                new_base_name = assemble_filename(fmt_author, fmt_series, fmt_volume, fmt_title, fmt_subtitle, fmt_edition, current_nlp)

                new_base_name = re.sub(r'[\\/*?:"<>|\n\r\t]', "_", new_base_name)
                new_base_name = re.sub(r'_{2,}', "_", new_base_name).strip(" _.")

                if not new_base_name:
                    print_error("Sanitized summary is empty. Cannot use as a filename.")
                    fail_count += 1
                else:
                    current_dir = os.path.dirname(file_path)
                    new_path = get_unique_new_path(current_dir, new_base_name, file_path)
                    
                    if not new_path:
                        print_error("Failed to determine a unique new path. Aborting rename process.")
                        fail_count += 1
                    else:
                        old_base_name = os.path.splitext(os.path.basename(file_path))[0]
                        new_file_name = os.path.basename(new_path)
                        final_new_base_name = os.path.splitext(new_file_name)[0]

                        print_step(f"Ready to rename from '{old_base_name}.pdf' to '{new_file_name}'.")
                        success = rename_file(file_path, new_path)
                        
                        if success:
                            success_count += 1
                            print_success("Primary PDF renamed successfully. Proceeding to rename associated files.")
                            rename_associated_files(current_dir, old_base_name, final_new_base_name, new_file_name)
                        else:
                            fail_count += 1
                            print_error("Primary PDF renaming failed. Associated files will not be renamed.")

            print_progress(1, total, prefix='Dropped File Progress', suffix='Complete', length=30)
            print_summary_box("Dropped File Processing Cycle", total, success_count, fail_count)

        except Exception as e:
            print_error(f"Critical error processing dropped file: {e}")
            print_summary_box("Dropped File Processing Cycle (Interrupted)", total, success_count, fail_count)


class MainWindow(QMainWindow):
    """Main application window containing the drop zone."""
    def __init__(self) -> None:
        try:
            print_step("Initializing MainWindow.")
            super().__init__()
            self.setWindowTitle("PDF Catalog Drop & Execute")
            self.resize(600, 400)

            print_step("Setting up central widget and layout.")
            self.central_widget = QWidget()
            self.setCentralWidget(self.central_widget)

            layout = QVBoxLayout()
            self.drop_zone = DropZone()
            layout.addWidget(self.drop_zone)

            self.central_widget.setLayout(layout)
            print_success("MainWindow initialized successfully.")
        except Exception as e:
            print_error(f"Error initializing MainWindow: {e}")

def main() -> None:
    """Main application entry point."""
    print_step("Application entry point reached.")
    try:
        print_step("Initializing QApplication.")
        app = QApplication(sys.argv)
        print_step("Creating MainWindow instance.")
        window = MainWindow()
        window.show()
        print_success("Application started successfully. Waiting for PDF drops...")
        sys.exit(app.exec_())
    except Exception as e:
        print_error(f"Error in main application loop: {e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_error("Process interrupted by user. Exiting.")
    except Exception as e:
        print_error(f"Fatal error: {e}")
