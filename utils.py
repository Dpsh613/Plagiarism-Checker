import re
import unicodedata
import pdfplumber

MAX_PDF_PAGES = 100
MAX_TEXT_CHARACTERS = 500_000
MAX_CHUNKS = 1_500

MATH_SYMBOLS = set("=+\\/^_{}$∑∞∫π∂√±×÷≠≈≤≥∈∀∃αβγδλμστφψω")

def _is_math_garble_line(line):
    """Drop only lines dominated by math symbols, never normal prose.

    A line is garble only if symbols make up a large share of it, so
    sentences like 'E=mc2' or 'client/server' survive while formula
    wreckage from PDF extraction is still removed.
    """
    stripped = line.strip()
    if len(stripped) < 10:
        return False
    symbols = sum(1 for ch in stripped if ch in MATH_SYMBOLS)
    return (symbols / len(stripped)) > 0.30


def normalize_text(text):
    if not text: return ""
    text = unicodedata.normalize('NFKD', text)

    # Remove citations [1], (Smith, 2020)
    text = re.sub(r'\[\d+(?:-\d+)?\]', '', text)
    text = re.sub(r'\([A-Za-z]+(?: et al\.)?, \d{4}\)', '', text)

    # Strip standalone heavy math garble line-by-line (density heuristic)
    text = "\n".join(line for line in text.split("\n") if not _is_math_garble_line(line))

    # Standard cleanup
    text = re.sub(r'-\n\s*', '', text)
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_text_from_pdf(pdf_path):
    """Returns (pages_data, info) where info reports silent-limit truncation."""
    pages_data = []
    info = {"truncated": False, "reason": None, "pages_read": 0}
    total_characters = 0
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) > MAX_PDF_PAGES:
                info["truncated"] = True
                info["reason"] = f"page_limit:{MAX_PDF_PAGES}"
            for i, page in enumerate(pdf.pages):
                if i >= MAX_PDF_PAGES:
                    break
                try:
                    # Crop out headers/footers (top 10%, bottom 10%)
                    bbox = page.bbox
                    x0, y0, x1, y1 = bbox
                    page_height = y1 - y0
                    crop_rect = (x0, y0 + (page_height * 0.10), x1, y0 + (page_height * 0.90))
                    cropped_page = page.crop(bbox=crop_rect)
                    text = cropped_page.extract_text(x_tolerance=2, y_tolerance=2)
                except:
                    text = page.extract_text()

                if text:
                    remaining_characters = MAX_TEXT_CHARACTERS - total_characters
                    if remaining_characters <= 0:
                        info["truncated"] = True
                        info["reason"] = info["reason"] or "char_limit"
                        break
                    cleaned_text = normalize_text(text)
                    if len(cleaned_text) > remaining_characters:
                        info["truncated"] = True
                        info["reason"] = info["reason"] or "char_limit"
                        cleaned_text = cleaned_text[:remaining_characters]
                    if len(cleaned_text) > 50:
                        pages_data.append({"page": i + 1, "text": cleaned_text})
                        total_characters += len(cleaned_text)
            info["pages_read"] = min(len(pdf.pages), MAX_PDF_PAGES)
    except Exception:
        return [], {"truncated": False, "reason": "extraction_failed", "pages_read": 0}
    return pages_data, info

def extract_text_from_document(file_path):
    """Extract supported local documents with resource limits applied.

    Returns (pages_data, info); oversized text is truncated (not rejected)
    with info["truncated"] set so callers can warn the user.
    """
    if file_path.lower().endswith(".txt"):
        try:
            with open(file_path, "r", encoding="utf-8", errors="strict") as text_file:
                text = text_file.read(MAX_TEXT_CHARACTERS + 1)
            truncated = len(text) > MAX_TEXT_CHARACTERS
            cleaned_text = normalize_text(text[:MAX_TEXT_CHARACTERS])
            info = {"truncated": truncated, "reason": "char_limit" if truncated else None, "pages_read": 1}
            return ([{"page": 1, "text": cleaned_text}], info) if len(cleaned_text) > 50 else ([], info)
        except (OSError, UnicodeDecodeError):
            return [], {"truncated": False, "reason": "extraction_failed", "pages_read": 0}
    return extract_text_from_pdf(file_path)

def get_sliding_windows(pages_data, window_size=40, overlap=15):
    """
    Industry standard: break text into overlapping chunks of words.
    Much safer than relying on periods (which math formulas ruin).
    Returns (chunks, capped) so callers can warn when MAX_CHUNKS truncates.
    """
    chunks_with_meta = []
    for entry in pages_data:
        words = entry['text'].split()
        if not words: continue

        for i in range(0, len(words), window_size - overlap):
            chunk = " ".join(words[i:i + window_size])
            if len(chunk) > 30: # Ignore tiny fragments
                chunks_with_meta.append({
                    "text": chunk,
                    "page": entry['page']
                })
                if len(chunks_with_meta) >= MAX_CHUNKS:
                    return chunks_with_meta, True
    return chunks_with_meta, False
