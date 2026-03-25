"""NERC PDF parsing service — extracts feeder table data from NERC monthly energy cap PDFs."""
import re
from typing import List, Optional

import fitz  # PyMuPDF

# Table columns in order as they appear in the NERC PDF
# STATE | BUSINESS UNIT | FEEDER NAME | NON-MD SERVICE BAND | CAP (kWh)
VALID_BANDS = {"A", "B", "C", "D", "E"}


def parse_nerc_pdf(pdf_bytes: bytes) -> List[dict]:
    """
    Extract feeder rows from a NERC monthly energy cap PDF.
    Returns a list of dicts with keys: state, business_unit, name, tariff_band, cap_kwh
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    feeders = []

    for page in doc:
        # Extract words with their bounding boxes for column detection
        words = page.get_text("words")  # (x0, y0, x1, y1, word, block, line, word_idx)
        rows = _group_words_into_rows(words)
        feeders.extend(_parse_rows(rows))

    return feeders


def _group_words_into_rows(words: list) -> List[List[tuple]]:
    """Group words into rows based on their vertical (y) position."""
    if not words:
        return []

    # Sort by y0 then x0
    words_sorted = sorted(words, key=lambda w: (round(w[1] / 5) * 5, w[0]))

    rows = []
    current_row = [words_sorted[0]]
    current_y = words_sorted[0][1]

    for word in words_sorted[1:]:
        # Words within 5 pts vertically are on the same row
        if abs(word[1] - current_y) <= 5:
            current_row.append(word)
        else:
            rows.append(sorted(current_row, key=lambda w: w[0]))
            current_row = [word]
            current_y = word[1]

    if current_row:
        rows.append(sorted(current_row, key=lambda w: w[0]))

    return rows


def _parse_rows(rows: List[List[tuple]]) -> List[dict]:
    """
    Parse grouped rows into feeder dicts.
    Expected column layout (left to right):
      STATE | BUSINESS UNIT | FEEDER NAME | BAND | CAP
    """
    feeders = []

    for row in rows:
        text_parts = [w[4] for w in row]
        line = " ".join(text_parts).strip()

        # Skip header rows and empty lines
        if not line or _is_header_or_noise(line):
            continue

        feeder = _extract_feeder_from_row(row, text_parts)
        if feeder:
            feeders.append(feeder)

    return feeders


def _is_header_or_noise(line: str) -> bool:
    """Filter out header rows, page numbers, and document metadata."""
    noise_patterns = [
        r"^STATE\b",
        r"^BUSINESS\s+UNIT",
        r"^FEEDER\s+NAME",
        r"^NON.?MD",
        r"^SERVICE\s+BAND",
        r"^CAP",
        r"^Page\s*\|",
        r"^NIGERIAN\s+ELECTRICITY",
        r"^Order\s+No",
        r"^Monthly\s+Energy",
        r"^Energy\s+Consumed",
        r"^in\s+the\s+Nigerian",
        r"^\d+$",  # standalone page numbers
    ]
    for pattern in noise_patterns:
        if re.match(pattern, line, re.IGNORECASE):
            return True
    return False


def _extract_feeder_from_row(row: List[tuple], text_parts: List[str]) -> Optional[dict]:
    """
    Extract a feeder record from a row of words.
    Uses x-position of words to determine which column they belong to.
    Column boundaries (approximate, based on NERC PDF layout):
      STATE:         x < 230
      BUSINESS UNIT: 230 <= x < 450
      FEEDER NAME:   450 <= x < 700
      BAND:          700 <= x < 760
      CAP:           x >= 760
    """
    if not row:
        return None

    # Get page width reference from rightmost word
    col_state = []
    col_business_unit = []
    col_feeder_name = []
    col_band = []
    col_cap = []

    for word_tuple in row:
        x0 = word_tuple[0]
        word = word_tuple[4]

        if x0 < 230:
            col_state.append(word)
        elif x0 < 450:
            col_business_unit.append(word)
        elif x0 < 700:
            col_feeder_name.append(word)
        elif x0 < 760:
            col_band.append(word)
        else:
            col_cap.append(word)

    state = " ".join(col_state).strip()
    business_unit = " ".join(col_business_unit).strip()
    feeder_name = " ".join(col_feeder_name).strip()
    band = " ".join(col_band).strip().upper()
    cap_str = " ".join(col_cap).strip()

    # Validate — must have at least feeder name and a valid band
    if not feeder_name or band not in VALID_BANDS:
        return None

    cap_kwh = None
    try:
        cap_kwh = float(re.sub(r"[^\d.]", "", cap_str))
    except (ValueError, TypeError):
        pass

    return {
        "name": feeder_name,
        "state": state or None,
        "business_unit": business_unit or None,
        "tariff_band": band,
        "cap_kwh": cap_kwh,
    }
