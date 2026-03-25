"""NERC PDF parsing service."""
from typing import List

import fitz  # PyMuPDF


def parse_nerc_pdf(pdf_bytes: bytes) -> List[dict]:
    """
    Extract feeder data from a NERC PDF document.
    Returns a list of raw feeder dicts for further validation and storage.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    feeders = []

    for page in doc:
        text = page.get_text()
        # TODO: implement actual parsing logic based on NERC PDF structure
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        feeders.extend(_extract_feeders_from_lines(lines))

    return feeders


def _extract_feeders_from_lines(lines: List[str]) -> List[dict]:
    """Parse lines from a NERC PDF page into feeder records."""
    # Placeholder — real implementation depends on PDF layout
    return []
