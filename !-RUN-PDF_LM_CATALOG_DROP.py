import difflib
import glob
import importlib
import json
import logging
import os
import re
import shutil
import sys
import time
import traceback
import warnings
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
logging.getLogger("pypdf").setLevel(logging.ERROR)
os.environ.setdefault("QT_LOGGING_RULES", "*.debug=false;*.info=false;*.warning=false")

try:
    import pypdf
    from lmstd import ChatResponse, ListModelsResponse, LMStd
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QDragEnterEvent, QDropEvent
    from PyQt5.QtWidgets import (QApplication, QLabel, QMainWindow, QVBoxLayout,
                                 QWidget)
except ImportError as e:
    print(f"🔴 [ERROR] Required library missing: {e}. Install with: pip install pypdf lmstd PyQt5", file=sys.stderr)
    sys.exit(1)

try:
    import spacy
except ImportError:
    spacy = None

try:
    from langdetect import detect
except ImportError:
    detect = None

# Global event chain to track execution trace for each file
event_chain: List[str] = []


def clean_text_for_llm(value: Any) -> str:
    """Normalizes text to valid UTF-8 for LLM prompts and responses."""
    if value is None:
        return ""

    text = str(value)
    text = text.replace("\ufeff", "")
    text = text.replace("\x00", "")
    text = text.encode("utf-8", errors="replace").decode("utf-8")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch if ch.isprintable() or ch in "\n\t" else " " for ch in text)
    text = re.sub(r"[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def capitalize_first_letter(text: str) -> str:
    """Ensures the first alphabetic character starting a word in text is upper case."""
    if not text or text.upper() == "EMPTY":
        return text
    for i, ch in enumerate(text):
        if ch.isalpha():
            if i == 0 or not text[i - 1].isalnum():
                return text[:i] + ch.upper() + text[i + 1:]
            break
    return text


# Initialize the LM Studio client pointing to the local LM Studio server.
try:
    client = LMStd(base_url=os.environ.get("LMSTD_HOST", "http://localhost:1234"),
                   api_token=os.environ.get("LMSTD_APIKEY"))
except Exception as e:
    print(f"🔴 [Error] Failed to initialize LMStd client: {e}", file=sys.stderr)
    sys.exit(1)


def get_current_time() -> str:
    """Returns the current time formatted as HH:MM:SS."""
    try:
        return datetime.now().strftime('%H:%M:%S')
    except Exception as e:
        print(f"🔴 [Error] get_current_time failed: {e}", file=sys.stderr)
        return "00:00:00"


def print_step(message: str) -> None:
    """Prints a step in a process."""
    try:
        parts = message.split(":", 1)
        if len(parts) == 2:
            msg = f"[{get_current_time()}] 🔹 [STEP] [{parts[0].strip()}] {parts[1].strip()}"
        else:
            msg = f"[{get_current_time()}] 🔹 [STEP] [{message.strip()}] STARTING"
        print(msg)
        event_chain.append(msg)
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] print_step failed: {e}", file=sys.stderr)


def print_success(message: str) -> None:
    """Prints a successful step completion."""
    try:
        parts = message.split(":", 1)
        if len(parts) == 2:
            msg = f"[{get_current_time()}] ✅ [SUCCESS] [{parts[0].strip()}] {parts[1].strip()}"
        else:
            msg = f"[{get_current_time()}] ✅ [SUCCESS] [{message.strip()}] SUCCESS"
        print(msg)
        event_chain.append(msg)
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] print_success failed: {e}", file=sys.stderr)


def print_error(message: str) -> None:
    """Prints an error message."""
    try:
        parts = message.split(":", 1)
        if len(parts) == 2:
            msg = f"[{get_current_time()}] 🔴 [ERROR] [{parts[0].strip()}] {parts[1].strip()}"
        else:
            msg = f"[{get_current_time()}] 🔴 [ERROR] [{message.strip()}] ERROR"
        print(msg, file=sys.stderr)
        event_chain.append(msg)
    except Exception as e:
        print(f"[{get_current_time()}] 🔴 [Error] print_error failed: {e}", file=sys.stderr)


def print_progress(current: int, total: int, prefix: str = '', suffix: str = '', decimals: int = 1, length: int = 50, fill: str = '█', printEnd: str = "\n") -> None:
    """Call in a loop to create terminal progress bar."""
    try:
        if total == 0:
            return
        percent = ("{0:." + str(decimals) + "f}").format(100 *
                                                         (current / float(total)))
        filledLength = int(length * current // total)
        bar = fill * filledLength + '-' * (length - filledLength)
        print(
            f'[{get_current_time()}] 🔄 {prefix} |{bar}| {percent}% {suffix}', end=printEnd)
    except Exception as e:
        print_error(f"Failed to print progress: {e}")


def print_summary_box(title: str, total: int, success: int, fails: int) -> None:
    """
    Prints a visually clear box summarizing the cycle.
    """
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
        print_error(f"Failed to print summary box: {e}")


FIELD_PROMPTS: Dict[str, str] = {
    "Author": """Extract the primary author (person or institution). 
Rules: Return only the first/main author. Omit titles (Dr., Prof.). Use well-known acronyms for institutions (e.g., WHO). Return EMPTY if none.""",

    "Series": """Extract the macro-group or collection name (e.g., 'Nature', 'The Lord of the Rings'). 
Rules: Do not include the main title or publisher name. Return EMPTY if the document is standalone.""",

    "Volume": """Extract the volume, issue, or sequence number within its series. 
Rules: Return the specific identifier (e.g., 'Vol. 2', 'Issue 4'). Ignore dates unless they act as the primary identifier. Return EMPTY if none.""",

    "Title": """Extract the main title. 
Rules: Exclude the subtitle, author, and labels like 'Title:'. If a title is not found, you must make a title as a summary with up to 100 characters of the content of the document.""",

    "Subtitle": """Extract the secondary/explanatory subtitle. 
Rules: Exclude labels like 'Subtitle:'. Return EMPTY if no clear subtitle exists.""",

    "Edition": """Extract the edition version (e.g., '1st Edition', 'Revised'). 
Rules: Exclude dates, volumes, or publishers. Return EMPTY if none."""
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
    if spacy is None:
        print_step("[Load Spacy Model]: Spacy is not installed; using lightweight rule-based fallback.")
        return None

    primary = spacy_models_map.get(lang_code, "xx_ent_wiki_sm")
    candidates = [primary] + [m for m in ("xx_ent_wiki_sm", "pt_core_news_sm", "en_core_web_sm") if m != primary]

    for model_name in candidates:
        if model_name in nlp_models_cache:
            print_success(f"[Load Spacy Model] Found in cache: {model_name}")
            return nlp_models_cache[model_name]
        try:
            print_step(
                f"[Load Spacy Model]: Loading Spacy model '{model_name}' for language '{lang_code}'")
            try:
                model_module = importlib.import_module(model_name)
                model = model_module.load()
            except (ImportError, AttributeError):
                model = spacy.load(model_name)
            nlp_models_cache[model_name] = model
            print_success(f"[Load Spacy Model] Loaded model: {model_name}")
            return model
        except Exception:
            continue

    print_step(f"[Load Spacy Model]: No Spacy model available for '{lang_code}'; using lightweight rule-based fallback.")
    return None


def abbreviate_words(text: str, nlp_model: Any, target_pos: List[str], preserve_first: bool = True) -> str:
    """Abbreviates words in text matching specific POS tags."""
    try:
        print_step("[Abbreviate Words] Abbreviating words based on POS tags.")
        if not text or text.upper() == "EMPTY":
            print_success("[Abbreviate Words] Empty text")
            return ""

        if nlp_model is None:
            words = text.split()
            out_words = []
            first_alpha_seen = False
            for word in words:
                has_alpha = any(c.isalpha() for c in word)
                is_candidate = has_alpha and len(word) > 2
                if has_alpha and preserve_first and not first_alpha_seen:
                    is_candidate = False
                    first_alpha_seen = True
                if is_candidate:
                    out_words.append(word[0].upper() + ".")
                else:
                    out_words.append(word)
            res = " ".join(out_words).strip()
        else:
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
                    out += word[0].upper() + "." + token.whitespace_
                else:
                    out += word + token.whitespace_

            res = out.strip()
        if res:
            res = capitalize_first_letter(res)
        print_success(
            f"[Abbreviate Words] Abbreviated result length: {len(res)}")
        return res
    except Exception as e:
        print_error(f"[Abbreviate Words] Failed to abbreviate words: {e}")
        return capitalize_first_letter(text) if text else text

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
            return capitalize_first_letter(text)

        parts = text.split()
        if len(parts) == 1:
            print_success("Formatting author: Single word author")
            return text.upper()

        last_name = parts[-1].upper()
        initials: List[str] = []

        text_to_analyze = " ".join(parts[:-1])
        if text_to_analyze.isupper():
            text_to_analyze = text_to_analyze.lower()

        if nlp_model is None:
            stopwords = {
                "de", "da", "do", "dos", "das", "e", "van", "von", "del",
                "la", "le", "di", "du", "and", "of", "the", "et"
            }
            for token_text in parts[:-1]:
                clean_text = re.sub(r'[^a-zA-ZÀ-ÿ]', '', token_text)
                if clean_text and clean_text.lower() not in stopwords:
                    initials.append(clean_text[0].upper() + ".")
        else:
            doc = nlp_model(text_to_analyze)

            for token in doc:
                clean_text = re.sub(r'[^a-zA-ZÀ-ÿ]', '', token.text)
                if clean_text and token.pos_ not in ["ADP", "CCONJ", "SCONJ", "DET", "PRON", "PART"]:
                    initials.append(clean_text[0].upper() + ".")

        if initials:
            res = f"{last_name}, {' '.join(initials)}"
        else:
            res = last_name

        res = capitalize_first_letter(res)
        print_success(f"Formatting author: Result: {res}")
        return res
    except Exception as e:
        print_error(f"Formatting author failed: {e}")
        return capitalize_first_letter(text) if text else text


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

        if nlp_model is None:
            minor_words = {
                "a", "o", "os", "as", "e", "ou", "de", "da", "do", "das", "dos",
                "em", "na", "no", "nas", "nos", "por", "para", "com", "sem", "um", "uma",
                "the", "of", "and", "in", "on", "at", "to", "for", "by", "with", "from", "an", "or"
            }
            tokens = re.findall(r'\S+|\s+', text)
            orig_tokens = re.findall(r'\S+|\s+', original_text)
            out_parts = []
            for idx, tok in enumerate(tokens):
                if tok.isspace():
                    out_parts.append(tok)
                    continue
                orig_tok = orig_tokens[idx] if idx < len(orig_tokens) else tok
                clean_alpha = re.sub(r'[^a-zA-ZÀ-ÿ]', '', tok)
                if clean_alpha and len(clean_alpha) <= 4 and orig_tok.isupper():
                    out_parts.append(orig_tok)
                elif clean_alpha.lower() in minor_words:
                    out_parts.append(tok.lower())
                else:
                    out_parts.append(tok.capitalize())
            res = "".join(out_parts).strip()
        else:
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
        if res:
            res = capitalize_first_letter(res)
        print_success("Formatting title case completed")
        return res
    except Exception as e:
        print_error(f"Formatting title case failed: {e}")
        return capitalize_first_letter(text) if text else text


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
        if len(name) <= 180:
            print_success("Assembling filename: No abbreviations needed")
            return name

        # Phase 1: Abbreviate Adverbs (ADV)
        adv_pos = ["ADV"]
        subtitle = abbreviate_words(subtitle, nlp_model, adv_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 180:
            print_success("Assembling filename: Abbreviated phase 1")
            return name
        title = abbreviate_words(title, nlp_model, adv_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 180:
            print_success("Assembling filename: Abbreviated phase 1")
            return name
        series = abbreviate_words(series, nlp_model, adv_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 180:
            print_success("Assembling filename: Abbreviated phase 1")
            return name

        # Phase 2: Abbreviate Adjectives and Verbs (ADJ, VERB)
        adj_verb_pos = ["ADJ", "VERB"]
        subtitle = abbreviate_words(subtitle, nlp_model, adj_verb_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 180:
            print_success("Assembling filename: Abbreviated phase 2")
            return name
        title = abbreviate_words(title, nlp_model, adj_verb_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 180:
            print_success("Assembling filename: Abbreviated phase 2")
            return name
        series = abbreviate_words(series, nlp_model, adj_verb_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 180:
            print_success("Assembling filename: Abbreviated phase 2")
            return name

        # Phase 3: Abbreviate Nouns and Proper Nouns (NOUN, PROPN)
        noun_pos = ["NOUN", "PROPN"]
        subtitle = abbreviate_words(subtitle, nlp_model, noun_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 180:
            print_success("Assembling filename: Abbreviated phase 3")
            return name
        title = abbreviate_words(title, nlp_model, noun_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 180:
            print_success("Assembling filename: Abbreviated phase 3")
            return name
        series = abbreviate_words(series, nlp_model, noun_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 180:
            print_success("Assembling filename: Abbreviated phase 3")
            return name

        # Phase 4: Abbreviate other fields aggressively (Edition, Volume)
        all_pos = ["ADV", "ADJ", "VERB", "NOUN", "PROPN"]
        edition = abbreviate_words(edition, nlp_model, all_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 180:
            print_success("Assembling filename: Abbreviated phase 4")
            return name
        volume = abbreviate_words(volume, nlp_model, all_pos)
        name = build_name(series, volume, title, subtitle, edition)
        if len(name) <= 180:
            print_success("Assembling filename: Abbreviated phase 4")
            return name

        # Phase 5: Force truncate characters if still > 180
        if len(name) > 180:
            name = name[:180].strip()
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
            print_success("Removing overlapping phrases: Cleaned to empty")
            return "EMPTY"

        if cleaned_text != current_text:
            cleaned_text = remove_overlapping_phrases(
                cleaned_text, previous_text)

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
                cleaned_result = remove_overlapping_phrases(
                    cleaned_result, prev_value)
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
    print_step(
        f"Determining pages to extract for a PDF with {total_pages} total pages.")
    pages_to_extract: List[int] = []
    try:
        if total_pages > 33:
            print_step(
                "PDF has > 33 pages. Selecting first 11, middle 11, and last 11.")
            mid_start = max(0, (total_pages // 2) - 5)
            pages_to_extract = sorted(set(
                list(range(min(11, total_pages))) +
                list(range(mid_start, min(mid_start + 11, total_pages))) +
                list(range(max(0, total_pages - 11), total_pages))
            ))
        else:
            print_step("PDF has <= 33 pages. Selecting all pages.")
            pages_to_extract = list(range(total_pages))
        print_success(
            f"Successfully determined {len(pages_to_extract)} pages to extract.")
        return pages_to_extract
    except Exception as e:
        print_error(f"Error determining pages to extract: {e}")
        return []


def extract_text_from_pages(reader: pypdf.PdfReader, pages_to_extract: List[int]) -> str:
    """Extracts text from specified pages of a PDF reader object."""
    total = len(pages_to_extract)
    print_step(f"Starting extraction cycle for {total} selected pages.")
    text = ""
    success_count = 0
    fail_count = 0

    try:
        for idx, page_num in enumerate(pages_to_extract):
            try:
                page = reader.pages[page_num]
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
                success_count += 1
            except Exception as page_err:
                print_error(
                    f"Error extracting text from page {page_num + 1}: {page_err}")
                fail_count += 1
        print_success(
            f"Successfully finished text extraction loop. Total characters: {len(text)}")
        print_summary_box("Page Extraction Cycle", total,
                          success_count, fail_count)
        return text.strip()
    except Exception as e:
        print_error(f"Critical error during text extraction loop: {e}")
        print_summary_box("Page Extraction Cycle (Interrupted)",
                          total, success_count, fail_count)
        return ""


def extract_pdf_text(file_path: str) -> str:
    """Opens a PDF file and extracts text content from it."""
    print_step(f"Starting text extraction for PDF file: '{file_path}'")
    text = ""
    try:
        print_step(f"Opening file '{file_path}' in binary read mode.")
        with open(file_path, 'rb') as pdf_file:
            print_success("File opened successfully.")
            print_step("Initializing pypdf PdfReader.")
            reader = pypdf.PdfReader(pdf_file)
            if getattr(reader, "is_encrypted", False):
                try:
                    reader.decrypt("")
                except Exception:
                    pass
            total_pages = len(reader.pages)
            print_success(
                f"PDF reader initialized successfully. Total pages found: {total_pages}.")
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
        safe_pdf_text = clean_text_for_llm(pdf_text)
        full_prompt = f"{master_prompt}\n{safe_pdf_text}"

        if client is None:
            raise ConnectionError("LM Studio client is not initialized.")

        safe_input = clean_text_for_llm(full_prompt)
        safe_sys = clean_text_for_llm("You are a helpful assistant specialized in extracting specific information from documents into JSON format. You only respond with raw, valid JSON.")
        for attempt in range(1, 4):
            content = None
            try:
                print_step(f"Querying AI model for fields: Attempt {attempt}/3")
                response: ChatResponse = client.chat(
                    system_prompt=safe_sys,
                    input_data=safe_input,
                    temperature=0.0,
                )
                if "output" in response:
                    for item in response.get("output", []):
                        if item.get("type") == "message":
                            content = item.get("content")
                            break
                if content:
                    break
                if attempt < 3:
                    print_step(f"LM Studio Retry: Empty response on attempt {attempt}/3. Retrying...")
                    time.sleep(attempt)
            except Exception as api_err:
                if attempt < 3:
                    print_step(f"LM Studio Retry: Transient error on attempt {attempt}/3 ({api_err}). Retrying...")
                    time.sleep(attempt * 2)
                else:
                    raise api_err

        if not content:
            print_error(
                "Querying AI model for fields failed: Empty response content")
            return {f: "EMPTY" for f in fields}

        content = clean_text_for_llm(content).strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            extracted_data = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                candidate = re.sub(r",\s*\}", "}", match.group(0))
                extracted_data = json.loads(candidate)
            else:
                raise

        if not isinstance(extracted_data, dict):
            raise json.JSONDecodeError("Expected JSON object", content, 0)

        result = {}
        for field in fields:
            val = extracted_data.get(field)
            if val is None and isinstance(extracted_data, dict):
                val = next((v for k, v in extracted_data.items() if k.lower() == field.lower()), "EMPTY")
            if val is None:
                val = "EMPTY"
            if not isinstance(val, str):
                val = str(val)
            val = val.strip().replace('\n', ' ').replace('\r', '')
            val = val.strip('"').strip("'")
            if val and val.upper() != "EMPTY":
                val = capitalize_first_letter(val)
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
    print_step(
        f"Generating a unique new file path for base name '{new_base_name}'.")
    try:
        new_file_name = f"{new_base_name}.pdf"
        new_path = os.path.join(current_dir, new_file_name)

        print_step(f"Checking if path '{new_path}' already exists.")
        if os.path.exists(new_path) and original_path.lower() != new_path.lower():
            print_step(
                "Path already exists. Finding a unique filename with a counter.")
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
    print_step(
        f"Attempting to rename '{os.path.basename(old_path)}' to '{os.path.basename(new_path)}'.")
    last_error = None
    for attempt in range(1, 4):
        try:
            os.rename(old_path, new_path)
            print_success(
                f"Successfully renamed file to '{os.path.basename(new_path)}'.")
            return True
        except FileNotFoundError:
            print_error(f"Original file '{old_path}' not found for renaming.")
            return False
        except PermissionError as e:
            last_error = f"Permission denied when renaming '{old_path}': {e}"
            if attempt < 3:
                time.sleep(0.4 * attempt)
                continue
        except OSError as e:
            try:
                shutil.move(old_path, new_path)
                print_success(
                    f"Successfully moved file to '{os.path.basename(new_path)}'.")
                return True
            except Exception as move_err:
                last_error = f"Error renaming/moving file '{old_path}' to '{new_path}': {move_err}"
                if attempt < 3:
                    time.sleep(0.4 * attempt)
                    continue
        except Exception as e:
            last_error = f"Error renaming file '{old_path}' to '{new_path}': {e}"
            break

    print_error(last_error or f"Failed to rename '{old_path}'.")
    return False


def rename_associated_files(current_dir: str, old_base_name: str, final_new_base_name: str, new_pdf_name: str) -> None:
    """
    Searches for and renames other files in the directory that share the same old base name.
    Includes a progress cycle.
    """
    print_step(
        f"Searching for associated files with base name '{old_base_name}' in '{current_dir}'.")
    success_count = 0
    fail_count = 0
    total = 0

    try:
        files_in_dir = os.listdir(current_dir)
        total = len(files_in_dir)
        print_success(
            f"Found {total} files in directory. Filtering associated files.")

        for idx, f in enumerate(files_in_dir):
            print_step(f"Checking file for association: {f}")
            f_path = os.path.join(current_dir, f)
            try:
                if not os.path.isfile(f_path):
                    continue

                f_base_name, f_ext = os.path.splitext(f)

                # Check if this file is an associated file
                if f_base_name == old_base_name and f != new_pdf_name:
                    print_step(f"Found associated file: '{f}'")
                    new_f_name = f"{final_new_base_name}{f_ext}"
                    new_f_path = os.path.join(current_dir, new_f_name)

                    print_step(
                        f"Checking if target path '{new_f_path}' exists.")
                    if os.path.exists(new_f_path) and f_path.lower() != new_f_path.lower():
                        counter = 2
                        while os.path.exists(new_f_path) and f_path.lower() != new_f_path.lower():
                            new_f_name = f"{final_new_base_name} ({counter}){f_ext}"
                            new_f_path = os.path.join(current_dir, new_f_name)
                            counter += 1

                    print_step(
                        f"Attempting to rename associated file '{f}' to '{new_f_name}'.")
                    if rename_file(f_path, new_f_path):
                        print_success(
                            f"Renamed associated file '{f}' to '{new_f_name}'")
                        success_count += 1
                    else:
                        print_error(f"Failed to rename associated file '{f}'.")
                        fail_count += 1
            except Exception as file_err:
                print_error(
                    f"Error processing potential associated file '{f}': {file_err}")
                fail_count += 1

        print_success("Completed scanning and renaming associated files.")
        if success_count > 0 or fail_count > 0:
            print_summary_box("Associated Files Renaming",
                              success_count + fail_count, success_count, fail_count)

    except Exception as e:
        print_error(f"Error during associated files renaming process: {e}")


def handle_file_error(file_path: str, current_dir: str, error_log: str) -> None:
    """
    Moves the file to '!-ERRORS' to prevent it from being endlessly processed.
    Also attempts to move related files sharing the same basename.
    Saves a detailed log file of the error.
    """
    print_step(f"Moving '{file_path}' to '!-ERRORS'...")
    def _unique_dest(dest_dir: str, fname: str) -> str:
        candidate = os.path.join(dest_dir, fname)
        b, e = os.path.splitext(fname)
        c = 2
        while os.path.exists(candidate):
            candidate = os.path.join(dest_dir, f"{b} ({c}){e}")
            c += 1
        return candidate

    base_name, ext = os.path.splitext(file_path)
    errors_dir = os.path.join(current_dir, "!-ERRORS")
    os.makedirs(errors_dir, exist_ok=True)
    error_path = _unique_dest(errors_dir, file_path)
    src_main = os.path.join(current_dir, file_path)

    try:
        if os.path.exists(src_main):
            shutil.move(src_main, error_path)
            print_success("Moved main file to '!-ERRORS'")

        # Save the error log
        log_file_path = _unique_dest(errors_dir, f"{base_name}.log")
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(event_chain) + "\n\n[FINAL ERROR]\n" + error_log)
        print_success(f"Saved error log to '{log_file_path}'")

        # Move related files
        for related_file in os.listdir(current_dir):
            if related_file != file_path and os.path.splitext(related_file)[0] == base_name:
                try:
                    shutil.move(os.path.join(current_dir, related_file),
                                _unique_dest(errors_dir, related_file))
                    print_success(
                        f"Moved related file '{related_file}' to '!-ERRORS'")
                except Exception as e:
                    print_error(
                        f"Failed to move related file {related_file}: {e}")
    except Exception as e:
        print_error(f"Failed to move main file {file_path}: {e}")

# --- GUI Components ---


class DropZone(QLabel):
    """A QLabel subclass that accepts PDF file drops."""

    def __init__(self) -> None:
        try:
            print_step("Initializing DropZone widget.")
            super().__init__()
            self.session_success_count = 0
            self.session_fail_count = 0
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setText(
                "Drag and Drop PDF File Here\n\n🔹 Action: Catalog Metadata\n(Extracts metadata and renames file)")
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
                if any(u.toLocalFile().lower().endswith('.pdf') for u in urls):
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
                for url in urls:
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith('.pdf') and os.path.isfile(file_path):
                        print_success(f"Valid PDF file dropped: {file_path}")
                        self.process_file(file_path)
                    else:
                        print_error(f"Dropped item is not a valid PDF file: {file_path}")
        except Exception as e:
            print_error(f"Error in dropEvent: {e}")

    def process_file(self, file_path: str) -> None:
        event_chain.clear()
        print_step(
            f"=== Beginning processing cycle for dropped file: {file_path} ===")
        cycle_success = 0
        cycle_fail = 0

        try:
            print_step("Attempting to extract text from dropped PDF.")
            text = extract_pdf_text(file_path)

            if not text:
                error_msg = "Failed to extract text or PDF is empty. Processing aborted."
                print_error(error_msg)
                handle_file_error(os.path.basename(file_path),
                                  os.path.dirname(file_path), error_msg)
                cycle_fail = 1
            else:
                print_success(f"Extracted {len(text)} characters of text.")
                print_step("Proceeding to generate catalog filename.")

                try:
                    print_step("Detecting language")
                    lang_code = detect(text) if detect is not None else "xx"
                    print_success(f"Language detected: {lang_code}")
                except Exception as e:
                    lang_code = "xx"
                    print_step(
                        f"Detecting language: Could not detect language ({e}), defaulting to (xx)")

                current_nlp = load_spacy_model(lang_code)

                fields = ["Author", "Series", "Volume",
                          "Title", "Subtitle", "Edition"]
                prompts = FIELD_PROMPTS

                raw_extracted_data = query_model_single_call(
                    text, fields, prompts)

                extracted_data: Dict[str, str] = {}
                for field in fields:
                    raw_result = raw_extracted_data.get(field, "EMPTY")
                    cleaned_result = clean_repetitive_fields(
                        field, raw_result, extracted_data)
                    extracted_data[field] = cleaned_result
                    print_step(f"Extracted {field}: {cleaned_result}")

                if extracted_data.get("Author", "EMPTY") == "EMPTY" and extracted_data.get("Series", "EMPTY") == "EMPTY" and extracted_data.get("Title", "EMPTY") == "EMPTY":
                    error_msg = "No Author, Series, or Title found. Skipping file."
                    print_error(error_msg)
                    handle_file_error(os.path.basename(
                        file_path), os.path.dirname(file_path), error_msg)
                    cycle_fail = 1
                    self.session_success_count += cycle_success
                    self.session_fail_count += cycle_fail
                    session_total = self.session_success_count + self.session_fail_count
                    print_progress(
                        1, 1, prefix='Dropped File Progress', suffix='Complete', length=30)
                    print_summary_box("Cycle Summary", 1,
                                      cycle_success, cycle_fail)
                    print_summary_box("Overall Session Summary",
                                      session_total, self.session_success_count, self.session_fail_count)
                    return

                fmt_author = capitalize_first_letter(format_author(
                    extracted_data["Author"], current_nlp))
                fmt_series = capitalize_first_letter(format_title_case_nlp(
                    extracted_data["Series"], current_nlp))
                fmt_volume = capitalize_first_letter(format_title_case_nlp(
                    extracted_data["Volume"], current_nlp))
                fmt_title = capitalize_first_letter(format_title_case_nlp(
                    extracted_data["Title"], current_nlp))
                fmt_subtitle = capitalize_first_letter(format_title_case_nlp(
                    extracted_data["Subtitle"], current_nlp))
                fmt_edition = capitalize_first_letter(format_title_case_nlp(
                    extracted_data["Edition"], current_nlp))

                if not fmt_title:
                    fmt_title = "No Title"

                new_base_name = assemble_filename(
                    fmt_author, fmt_series, fmt_volume, fmt_title, fmt_subtitle, fmt_edition, current_nlp)

                new_base_name = re.sub(
                    r'[\\/*?:"<>|\n\r\t]', "_", new_base_name)
                new_base_name = re.sub(
                    r'_{2,}', "_", new_base_name).strip(" _.")

                if not new_base_name:
                    error_msg = "Sanitized summary is empty. Cannot use as a filename."
                    print_error(error_msg)
                    handle_file_error(os.path.basename(
                        file_path), os.path.dirname(file_path), error_msg)
                    cycle_fail = 1
                else:
                    current_dir = os.path.dirname(file_path)
                    new_path = get_unique_new_path(
                        current_dir, new_base_name, file_path)

                    if not new_path:
                        error_msg = "Failed to determine a unique new path. Aborting rename process."
                        print_error(error_msg)
                        handle_file_error(os.path.basename(
                            file_path), os.path.dirname(file_path), error_msg)
                        cycle_fail = 1
                    else:
                        old_base_name = os.path.splitext(
                            os.path.basename(file_path))[0]
                        new_file_name = os.path.basename(new_path)
                        final_new_base_name = os.path.splitext(new_file_name)[
                            0]

                        print_step(
                            f"Ready to rename from '{old_base_name}.pdf' to '{new_file_name}'.")
                        success = rename_file(file_path, new_path)

                        if success:
                            cycle_success = 1
                            print_success(
                                "Primary PDF renamed successfully. Proceeding to rename associated files.")
                            rename_associated_files(
                                current_dir, old_base_name, final_new_base_name, new_file_name)
                        else:
                            cycle_fail = 1
                            print_error(
                                "Primary PDF renaming failed. Associated files will not be renamed.")

            self.session_success_count += cycle_success
            self.session_fail_count += cycle_fail
            session_total = self.session_success_count + self.session_fail_count

            print_progress(1, 1, prefix='Dropped File Progress',
                           suffix='Complete', length=30)
            print_summary_box("Cycle Summary", 1,
                              cycle_success, cycle_fail)
            print_summary_box("Overall Session Summary",
                              session_total, self.session_success_count, self.session_fail_count)

        except Exception as e:
            error_msg = f"Critical error processing dropped file: {e}\n{traceback.format_exc()}"
            print_error(error_msg)
            handle_file_error(os.path.basename(file_path),
                              os.path.dirname(file_path), error_msg)

            cycle_fail = 1
            self.session_fail_count += cycle_fail
            session_total = self.session_success_count + self.session_fail_count

            print_summary_box("Cycle Summary (Interrupted)",
                              1, cycle_success, cycle_fail)
            print_summary_box(
                "Overall Session Summary (Interrupted)", session_total, self.session_success_count, self.session_fail_count)


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
        print_success(
            "Application started successfully. Waiting for PDF drops...")
        sys.exit(app.exec_())
    except Exception as e:
        print_error(f"Error in main application loop: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"[{get_current_time()}] ℹ️ [LOG] Process interrupted by user. Exiting.")
        sys.exit(0)
    except Exception as e:
        print_error(f"Fatal error: {e}")
        sys.exit(1)
