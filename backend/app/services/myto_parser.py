"""MYTO PDF parser — uses Google Document AI Form Parser for table-aware extraction.

Document AI understands table structure natively, returning rows and cells directly.
This handles multi-row cells and small text far better than OCR-based approaches.
"""

import re
from typing import Any, Dict, List, Optional

import fitz
from google.api_core.client_options import ClientOptions
from google.cloud import documentai
from loguru import logger

from app.core.config import settings


# ---------------------------------------------------------------------------
# Document AI client
# ---------------------------------------------------------------------------

def _get_client() -> documentai.DocumentProcessorServiceClient:
    """Build a Document AI client using Application Default Credentials."""
    api_endpoint = f"{settings.DOCUMENT_AI_LOCATION}-documentai.googleapis.com"
    client_options = ClientOptions(api_endpoint=api_endpoint)
    return documentai.DocumentProcessorServiceClient(client_options=client_options)


def _processor_name() -> str:
    return (
        f"projects/{settings.DOCUMENT_AI_PROJECT_ID}"
        f"/locations/{settings.DOCUMENT_AI_LOCATION}"
        f"/processors/{settings.DOCUMENT_AI_PROCESSOR_ID}"
    )


# ---------------------------------------------------------------------------
# Street splitter
# ---------------------------------------------------------------------------

_AND_PATTERN = re.compile(r"\s+and\s+", re.IGNORECASE)


def split_streets(raw: str) -> List[str]:
    """
    Split a raw street string into individual street names.

    Separators: comma and ' and '
    '&' is NOT a separator — it is part of street/place names.
    """
    if not raw:
        return []
    text = _AND_PATTERN.sub(", ", raw.strip())
    return [p.strip() for p in text.split(",") if len(p.strip()) > 2]


# ---------------------------------------------------------------------------
# Document AI helpers
# ---------------------------------------------------------------------------

def _get_text(element: Any, full_text: str) -> str:
    """
    Extract the text for a Document AI layout element using its text anchors.
    Mirrors the pattern from Google's Document AI samples.
    """
    text = ""
    for segment in element.layout.text_anchor.text_segments:
        start = int(segment.start_index)
        end = int(segment.end_index)
        text += full_text[start:end]
    return text.strip()


# MYTO table header keywords used to identify the correct table on a page
_FEEDER_HEADER_KEYWORDS = {"feeder", "street", "location", "description"}


def _is_myto_table(header_row: documentai.Document.Page.Table.TableRow, full_text: str) -> bool:
    """
    Check if a table is the MYTO feeder table by inspecting its header cells.
    Requires at least 2 of the expected keywords to be present.
    """
    header_text = " ".join(
        _get_text(cell, full_text).lower()
        for cell in header_row.cells
    )
    matches = sum(1 for kw in _FEEDER_HEADER_KEYWORDS if kw in header_text)
    return matches >= 2


def _map_header_columns(
    header_row: documentai.Document.Page.Table.TableRow,
    full_text: str,
) -> Dict[int, str]:
    """
    Map column indices to semantic names based on header cell text.

    Column header variations seen across discos:
    - "S/N"
    - "BAND"
    - "FEEDER NAME"
    - "DESCRIPTION OF FEEDER LOCATION" / "DESCRIPTION OF\nFEEDER LOCATION"
    - "NAME OF MAJOR STREETS SERVED BY THE FEEDER"
    - "AVE PERFORMANCE", "CURRENT BAND", "REMARK", "MIN. SUPPLY DURATION" — ignored

    Priority: streets > location > feeder > band > sn
    The streets column always contains "street" — check this FIRST before feeder,
    because the streets header also contains the word "feeder".
    """
    col_map: Dict[int, str] = {}

    for idx, cell in enumerate(header_row.cells):
        # Normalise: lowercase, collapse whitespace/newlines to single space
        text = re.sub(r"\s+", " ", _get_text(cell, full_text).lower()).strip()

        if not text:
            continue

        # Streets column — check FIRST (header contains both "street" and "feeder")
        if "street" in text:
            col_map[idx] = "streets"

        # Location column
        elif "description" in text or (
            "location" in text and "feeder" not in text
        ):
            col_map[idx] = "location"

        # Feeder name column — "feeder name" or standalone "feeder name" cell
        elif "feeder" in text and "name" in text:
            col_map[idx] = "feeder"

        # Band column (Appendix 5 style — has BAND before FEEDER NAME)
        elif text in ("band", "current band"):
            col_map[idx] = "band"

        # S/N column
        elif text in ("s/n", "s", "sn", "no"):
            col_map[idx] = "sn"

    logger.debug(f"Raw header cells: { {idx: re.sub(chr(10), ' ', _get_text(cell, full_text)) for idx, cell in enumerate(header_row.cells)} }")
    return col_map


def _extract_rows_from_table(
    table: documentai.Document.Page.Table,
    full_text: str,
) -> List[Dict[str, str]]:
    """
    Extract feeder data rows from a Document AI table.

    Uses the header row to map columns, then reads each body row.
    Returns a list of dicts with keys: feeder, location, streets.
    """
    if not table.header_rows:
        return []

    col_map = _map_header_columns(table.header_rows[0], full_text)
    logger.debug(f"Column map: {col_map}")

    if "feeder" not in col_map.values() or "streets" not in col_map.values():
        logger.warning("Could not identify required columns (feeder, streets) in table")
        return []

    results = []
    for row in table.body_rows:
        entry: Dict[str, str] = {"feeder": "", "location": "", "streets": "", "band": ""}

        for idx, cell in enumerate(row.cells):
            semantic = col_map.get(idx)
            if semantic and semantic in entry:
                cell_text = _get_text(cell, full_text).replace("\n", " ").strip()
                entry[semantic] = cell_text

        if entry["feeder"] or entry["streets"]:
            results.append(entry)

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _strip_pages(pdf_bytes: bytes, skip: int = 10) -> bytes:
    """
    Remove the first `skip` pages from a PDF and return the remaining bytes.
    Uses PyMuPDF (fitz) which is already a project dependency.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = len(doc)

    if total <= skip:
        logger.warning(f"PDF has {total} pages — nothing left after skipping {skip}")
        doc.close()
        return pdf_bytes  # return original to avoid empty document

    # Delete pages 0 to skip-1 (0-indexed)
    doc.delete_pages(0, skip - 1)
    logger.info(f"Stripped first {skip} pages — {total - skip} pages remaining")

    trimmed = doc.tobytes()
    doc.close()
    return trimmed


def parse_myto_pdf(pdf_bytes: bytes, skip_pages: int = 0) -> Dict[str, Any]:
    """
    Parse a MYTO PDF using Google Document AI Form Parser.

    Document AI processes the entire PDF in one API call and returns
    structured table data — rows and cells — handling multi-row cells
    and small text natively.

    Returns:
        {
            "feeders": [
                {
                    "feeder_name": str,
                    "location_description": str,
                    "streets": [str, ...]
                },
                ...
            ],
            "pages": int,
            "parsed": int,
            "skipped": int,
        }
    """
    client = _get_client()
    processor = _processor_name()

    # Strip leading pages (cover, TOC, intro) before sending to Document AI
    if skip_pages > 0:
        pdf_bytes = _strip_pages(pdf_bytes, skip=skip_pages)
        logger.info(f"Skipping first {skip_pages} pages as requested")

    logger.info(f"Sending PDF to Document AI processor: {processor}")

    raw_document = documentai.RawDocument(
        content=pdf_bytes,
        mime_type="application/pdf",
    )
    request = documentai.ProcessRequest(
        name=processor,
        raw_document=raw_document,
    )

    try:
        result = client.process_document(request=request)
    except Exception as e:
        logger.error(f"Document AI processing failed: {e}", exc_info=True)
        raise

    document = result.document
    full_text = document.text
    total_pages = len(document.pages)

    logger.info(f"Document AI returned {total_pages} pages")

    all_rows: List[Dict[str, str]] = []

    for page_num, page in enumerate(document.pages, start=1):
        tables = page.tables
        logger.debug(f"Page {page_num}: {len(tables)} table(s) found")

        for table_idx, table in enumerate(tables):
            if not table.header_rows:
                continue

            if not _is_myto_table(table.header_rows[0], full_text):
                logger.debug(f"Page {page_num}, Table {table_idx}: not a MYTO feeder table, skipping")
                continue

            rows = _extract_rows_from_table(table, full_text)
            logger.info(f"Page {page_num}, Table {table_idx}: extracted {len(rows)} rows")
            all_rows.extend(rows)

    # Build final output
    feeders = []
    skipped = 0

    for row in all_rows:
        feeder_name = row.get("feeder", "").strip()
        if not feeder_name:
            skipped += 1
            continue

        feeders.append({
            "feeder_name": feeder_name,
            "location_description": row.get("location", "").strip(),
            "band": row.get("band", "").strip() or None,
            "streets": split_streets(row.get("streets", "")),
        })

    logger.info(f"MYTO parse complete: {len(feeders)} feeders, {skipped} skipped")

    return {
        "feeders": feeders,
        "pages": total_pages,
        "parsed": len(feeders),
        "skipped": skipped,
    }
