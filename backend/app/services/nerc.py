"""NERC PDF parsing service — Table extraction using PaddleOCR PPStructure."""

import io
import re
import warnings
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import numpy as np
from paddleocr import PPStructureV3
from PIL import Image
from loguru import logger

from app.utils.data_cleaner import DataCleaner

# Suppress PaddlePaddle warnings
warnings.filterwarnings('ignore', category=UserWarning, module='paddle')


VALID_BANDS = {"A", "B", "C", "D", "E"}
_cleaner = DataCleaner()

# Initialize PPStructure reader (lazy loading)
_table_engine = None


def _get_table_engine():
    """Get or initialize the PPStructure table engine (singleton pattern)."""
    global _table_engine
    if _table_engine is None:
        logger.info("Initializing PaddleOCR PPStructure for table recognition...")
        _table_engine = PPStructure(
            table=True,           # Enable table recognition
            ocr=True,             # Enable OCR
            show_log=False,       # Suppress logs
            lang='en',            # English language
            use_gpu=False         # Set to True if CUDA is available
        )
        logger.info("PPStructure initialized")
    return _table_engine


# ==============================
# MAIN PARSER
# ==============================

def parse_nerc_pdf(pdf_bytes: bytes) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Extract feeder rows from a NERC monthly energy cap PDF using table structure recognition.
    
    Process:
    1. Convert each PDF page to an image
    2. Use PPStructure to detect and extract table structure
    3. Parse table cells into structured feeder data
    
    Returns:
        Tuple of (list of feeder dicts, list of page statistics)
    """
    all_feeders: List[Dict[str, Any]] = []
    page_stats: List[Dict[str, Any]] = []
    
    try:
        # Get table engine
        engine = _get_table_engine()
        
        # Open PDF with PyMuPDF
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = len(pdf_document)
        
        logger.info(f"PDF parsing started: {page_count} pages detected")
        
        for page_num in range(page_count):
            page = pdf_document[page_num]
            
            # Convert page to image (higher DPI for better recognition)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom = ~144 DPI
            img_data = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_data))
            
            # Convert PIL Image to numpy array
            img_array = np.array(image)
            
            # Extract table structure
            logger.debug(f"Page {page_num + 1}: Running PPStructure table recognition...")
            
            result = engine(img_array)
            
            # Parse tables from result
            is_first_page = (page_num == 0)
            page_feeders, rows_processed, rows_skipped = _parse_table_structure(
                result, 
                page_num,
                skip_first_header=is_first_page
            )
            
            # Store page statistics
            page_stat = {
                "number": page_num + 1,
                "rows": rows_processed,
                "extracted": len(page_feeders),
                "skipped": rows_skipped
            }
            page_stats.append(page_stat)
            
            logger.info(
                f"Page {page_num + 1}: Processed {rows_processed} rows, "
                f"extracted {len(page_feeders)} feeders, skipped {rows_skipped}"
            )
            
            all_feeders.extend(page_feeders)
        
        pdf_document.close()
        
        logger.info(
            f"PDF parsing complete: {len(all_feeders)} feeders extracted from {page_count} pages"
        )
        return all_feeders, page_stats
        
    except Exception as e:
        logger.error(f"Error parsing PDF: {e}", exc_info=True)
        raise


def _parse_table_structure(
    result: List[Dict], 
    page_num: int,
    skip_first_header: bool = False
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Parse PPStructure result to extract feeder data from tables.
    
    Args:
        result: PPStructure output containing detected regions
        page_num: Page number (0-indexed)
        skip_first_header: If True, skip the first header row
        
    Returns:
        Tuple of (feeders list, rows processed count, rows skipped count)
    """
    feeders = []
    rows_processed = 0
    rows_skipped = 0
    header_skipped = False
    
    for region in result:
        # Check if this region is a table
        if region.get('type') == 'table':
            table_html = region.get('res', {}).get('html', '')
            
            if not table_html:
                continue
            
            # Parse HTML table to extract rows
            table_rows = _parse_html_table(table_html)
            
            logger.debug(f"Page {page_num + 1}: Found table with {len(table_rows)} rows")
            
            for row_idx, row_cells in enumerate(table_rows):
                # Skip header row
                if _is_header_row_cells(row_cells):
                    if skip_first_header and not header_skipped:
                        logger.debug(f"Page {page_num + 1}, Row {row_idx}: Skipped first header")
                        header_skipped = True
                        rows_skipped += 1
                        continue
                    else:
                        rows_skipped += 1
                        continue
                
                # Parse row into feeder
                feeder = _parse_table_row(row_cells, page_num, row_idx)
                if feeder:
                    feeders.append(feeder)
                    rows_processed += 1
                else:
                    rows_skipped += 1
    
    return feeders, rows_processed, rows_skipped


def _parse_html_table(html: str) -> List[List[str]]:
    """
    Parse HTML table string to extract cell values.
    
    Args:
        html: HTML table string
        
    Returns:
        List of rows, where each row is a list of cell values
    """
    rows = []
    
    # Extract all <tr> tags
    tr_pattern = re.compile(r'<tr>(.*?)</tr>', re.DOTALL)
    tr_matches = tr_pattern.findall(html)
    
    for tr_content in tr_matches:
        # Extract all <td> tags in this row
        td_pattern = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)
        td_matches = td_pattern.findall(tr_content)
        
        # Clean cell content (remove HTML tags, normalize whitespace)
        cells = []
        for cell in td_matches:
            # Remove HTML tags
            cell_text = re.sub(r'<[^>]+>', '', cell)
            # Normalize whitespace
            cell_text = ' '.join(cell_text.split())
            cells.append(cell_text.strip())
        
        if cells:
            rows.append(cells)
    
    return rows


def _is_header_row_cells(cells: List[str]) -> bool:
    """Check if a row of cells is a header row."""
    row_text = ' '.join(cells).upper()
    header_keywords = {"FEEDER NAME", "FEEDER", "STATE", "BUSINESS UNIT", "TARIFF", "BAND", "CAP", "KWH"}
    keyword_count = sum(1 for keyword in header_keywords if keyword in row_text)
    return keyword_count >= 2


def _parse_table_row(cells: List[str], page_num: int, row_idx: int) -> Optional[Dict[str, Any]]:
    """
    Parse a table row (list of cells) into a feeder dict.
    
    Expected columns:
    [STATE, BUSINESS_UNIT, FEEDER_NAME, BAND, CAP]
    or
    [BUSINESS_UNIT, FEEDER_NAME, BAND, CAP]
    
    Args:
        cells: List of cell values
        page_num: Page number
        row_idx: Row index
        
    Returns:
        Feeder dict or None if invalid
    """
    # Clean cells
    cells = [_clean_cell(cell) for cell in cells]
    
    # Filter empty cells
    non_empty = [c for c in cells if c]
    
    if len(non_empty) < 3:
        logger.debug(f"Page {page_num + 1}, Row {row_idx}: Insufficient cells ({len(non_empty)})")
        return None
    
    # Try to identify columns based on cell count and content
    state = None
    business_unit = None
    feeder_name = None
    band = None
    cap_kwh = 0.0
    
    # Expected format: 5 columns
    if len(cells) >= 5:
        state = cells[0]
        business_unit = cells[1]
        feeder_name = cells[2]
        band = _extract_band_from_cell(cells[3])
        cap_kwh = _extract_cap_from_cell(cells[4])
    # Alternative format: 4 columns (no state)
    elif len(cells) == 4:
        business_unit = cells[0]
        feeder_name = cells[1]
        band = _extract_band_from_cell(cells[2])
        cap_kwh = _extract_cap_from_cell(cells[3])
    # Minimal format: 3 columns
    elif len(cells) == 3:
        feeder_name = cells[0]
        band = _extract_band_from_cell(cells[1])
        cap_kwh = _extract_cap_from_cell(cells[2])
    else:
        logger.debug(f"Page {page_num + 1}, Row {row_idx}: Unexpected column count ({len(cells)})")
        return None
    
    # Validate band
    if not band or band not in VALID_BANDS:
        logger.debug(f"Page {page_num + 1}, Row {row_idx}: Invalid band '{band}'")
        return None
    
    # Validate feeder name
    if not feeder_name or len(feeder_name) < 2:
        logger.debug(f"Page {page_num + 1}, Row {row_idx}: Invalid feeder name")
        return None
    
    # Filter metadata
    invalid_names = {"IN", "ENERGY", "CONSUMED", "FEBRUARY", "MARCH", "JANUARY", "APRIL", "MAY", "JUNE", 
                     "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER", "ORDER", "NO"}
    if feeder_name.upper() in invalid_names:
        logger.debug(f"Page {page_num + 1}, Row {row_idx}: Metadata row - '{feeder_name}'")
        return None
    
    # Clean and normalize
    feeder_name = feeder_name.strip().upper()
    formatted_address = _cleaner.clean_feeder_name(feeder_name)
    
    return {
        "state": state.upper() if state else None,
        "business_unit": business_unit.upper() if business_unit else None,
        "name": feeder_name,
        "formatted_address": formatted_address,
        "tariff_band": band,
        "cap_kwh": cap_kwh,
    }


# ==============================
# HELPER FUNCTIONS
# ==============================

def _clean_cell(cell: str) -> str:
    """Clean a table cell value."""
    if not cell:
        return ""
    # Remove pipes, underscores, extra whitespace
    cell = cell.replace('|', ' ').replace('_', ' ')
    cell = re.sub(r'\s+', ' ', cell)
    return cell.strip()


def _extract_band_from_cell(cell: str) -> str:
    """Extract band letter from a cell."""
    cell = cell.upper().strip()
    
    # Try exact match
    if cell in VALID_BANDS:
        return cell
    
    # Try to find band letter
    match = re.search(r'([A-E])', cell)
    if match:
        return match.group(1)
    
    return ""


def _extract_cap_from_cell(cell: str) -> float:
    """Extract numeric cap value from a cell."""
    cell = cell.strip().replace(",", "").replace("O", "0").replace("o", "0")
    
    # Extract number
    match = re.search(r'\d+\.?\d*', cell)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return 0.0
    
    return 0.0
