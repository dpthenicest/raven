"""NERC PDF parsing service — Page-by-page text recognition using PaddleOCR."""

import io
import re
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF
import numpy as np
from loguru import logger
from paddleocr import PaddleOCR
from PIL import Image

# Global singleton for the OCR engine
_ocr_engine = None


def _get_ocr_engine():
    """
    Initializes PaddleOCR with basic configuration.
    """
    global _ocr_engine
    if _ocr_engine is None:
        logger.info("Initializing PaddleOCR...")
        _ocr_engine = PaddleOCR(
            use_angle_cls=True,
            lang='en',
            det_db_thresh=0.2,      # Lower threshold to catch more text (default 0.3)
            det_db_box_thresh=0.4,  # Lower box threshold (default 0.6)
        )
        logger.info("PaddleOCR initialized")
    return _ocr_engine


class RavenPDFParser:
    VALID_BANDS = {"A", "B", "C", "D", "E"}
    
    def __init__(self):
        self.last_state = None
        self.last_bu = None
    
    def parse(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """
        Parse NERC PDF with dynamic column detection and fill-down logic.
        
        Returns:
            Dict with:
            - feeders: List of feeder dicts
            - pages: List of page metadata
        """
        extracted_feeders = []
        page_metadata = []
        rejected_rows = []  # Track rejected rows with details
        
        ocr = _get_ocr_engine()
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        logger.info(f"PDF parsing started: {len(pdf_doc)} pages detected")
        
        # Track if we've found the header (only needed once for the entire document)
        column_boundaries = None
        
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            # Use 3x resolution for good balance between speed and accuracy
            pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
            img = np.array(Image.open(io.BytesIO(pix.tobytes("png"))))
            
            logger.debug(f"Page {page_num + 1}: Running PaddleOCR text recognition...")
            
            # 1. OCR text detection
            result = ocr.ocr(img)
            if not result or not result[0]:
                logger.debug(f"Page {page_num + 1}: No text detected")
                page_metadata.append({
                    "number": page_num + 1,
                    "total_rows": 0,
                    "rows_extracted": 0
                })
                continue
            
            # 2. Extract raw items with coordinates
            raw_items = self._process_ocr_output(result[0])
            
            # 3. Group text into rows based on Y-coordinates
            rows = self._group_into_rows(raw_items)
            
            # 4. Dynamic Column Detection (only on first page or if not yet found)
            start_row_idx = 0
            if column_boundaries is None:
                column_boundaries, header_row_idx = self._detect_columns_with_index(rows)
                start_row_idx = header_row_idx + 1  # Skip header on first page
                logger.debug(f"Page {page_num + 1}: Header found at row {header_row_idx}, starting data extraction from row {start_row_idx}")
                logger.debug(f"Page {page_num + 1}: Column boundaries: {column_boundaries} (total: {len(column_boundaries)} columns)")
            else:
                # On subsequent pages, start from the first row (no header to skip)
                start_row_idx = 0
                logger.debug(f"Page {page_num + 1}: Using existing column boundaries, processing all rows")
            
            # 5. Map row text to the detected columns
            page_feeders = []
            page_fallback_count = 0
            i = start_row_idx
            while i < len(rows):
                # Skip rows before the data starts
                if i < start_row_idx:
                    i += 1
                    continue
                
                row_items = rows[i]
                
                # Debug: Show first 3 data rows on each page
                if i - start_row_idx < 3:
                    row_preview = " | ".join([item['text'] for item in row_items])
                    logger.debug(f"Page {page_num + 1}, Row {i}: {row_preview}")
                
                # Check if next rows are continuations (empty state/bu columns)
                # and merge them into current row
                merged_row_items = list(row_items)
                continuation_count = 0
                j = i + 1
                while j < len(rows):
                    next_row = rows[j]
                    # Parse next row to check if it's a continuation
                    next_col_data = self._map_row_to_columns(next_row, column_boundaries)
                    
                    # Debug: Show what we're checking
                    next_preview = " | ".join([item['text'] for item in next_row])
                    logger.debug(f"Page {page_num + 1}, Row {j}: Checking continuation - state:'{next_col_data[0]}', bu:'{next_col_data[1]}', preview: {next_preview}")
                    
                    # If state and business unit are empty, it's a continuation
                    if not next_col_data[0].strip() and not next_col_data[1].strip():
                        logger.debug(f"Page {page_num + 1}, Row {j}: IS CONTINUATION - merging with row {i}")
                        # Merge the row items
                        merged_row_items.extend(next_row)
                        continuation_count += 1
                        j += 1
                    else:
                        logger.debug(f"Page {page_num + 1}, Row {j}: NOT continuation - stopping merge")
                        break
                
                if continuation_count > 0:
                    logger.debug(f"Page {page_num + 1}, Row {i}: Merged {continuation_count} continuation rows")
                
                # Parse the merged row
                feeder, used_fallback = self._parse_structured_row(
                    merged_row_items, column_boundaries, page_num + 1, i
                )
                if feeder:
                    page_feeders.append(feeder)
                    if used_fallback:
                        page_fallback_count += 1
                elif feeder is None:
                    # Row was rejected, track it
                    rejected_info = self._get_rejection_info(merged_row_items, column_boundaries, page_num + 1, i)
                    if rejected_info:
                        rejected_rows.append(rejected_info)
                
                # Move to next unprocessed row
                i = j if j > i + 1 else i + 1
            
            logger.info(
                f"Page {page_num + 1}: Extracted {len(page_feeders)} feeders from {len(rows)} rows (fallbacks: {page_fallback_count})"
            )
            
            extracted_feeders.extend(page_feeders)
            page_metadata.append({
                "number": page_num + 1,
                "total_rows": len(rows),
                "rows_extracted": len(page_feeders),
                "fallback_count": page_fallback_count
            })
        
        pdf_doc.close()
        
        logger.info(f"PDF parsing complete: {len(extracted_feeders)} feeder rows extracted")
        
        return {
            "feeders": extracted_feeders,
            "pages": page_metadata,
            "rejected_rows": rejected_rows
        }
    
    def _process_ocr_output(self, ocr_data: List) -> List[Dict]:
        """Extract text items with bounding box coordinates."""
        items = []
        for line in ocr_data:
            box, (text, score) = line
            items.append({
                "text": text.strip(),
                "x0": box[0][0],
                "y0": box[0][1],
                "x1": box[2][0],
                "y1": box[2][1],
                "conf": score
            })
        return items
    
    def _detect_columns_with_index(self, rows: List[List[Dict]]) -> tuple[List[float], int]:
        """
        Finds the table header row by looking for keywords and returns column boundaries and row index.
        Returns: (column_boundaries, header_row_index)
        """
        if not rows:
            return [], -1
        
        # Look for the header row containing table column keywords
        header_keywords = ['STATE', 'BUSINESS', 'FEEDER', 'BAND', 'CAP', 'SERVICE']
        
        header_row_idx = -1
        for idx, row in enumerate(rows):
            row_text = ' '.join([item['text'].upper() for item in row])
            # Check if this row contains multiple header keywords
            keyword_matches = sum(1 for keyword in header_keywords if keyword in row_text)
            if keyword_matches >= 3:  # At least 3 keywords found
                logger.debug(f"Found header row at index {idx}: {row_text}")
                header_row_idx = idx
                break
        
        if header_row_idx == -1:
            # No header found, use first row
            logger.debug("No header row found, using first row as fallback")
            header_row_idx = 0
        
        # Now analyze the first few DATA rows (after header) to determine actual column positions
        # This is more reliable than using the header which might have merged text
        data_rows_to_analyze = []
        for i in range(header_row_idx + 1, min(header_row_idx + 10, len(rows))):
            if i < len(rows):
                data_rows_to_analyze.append(rows[i])
        
        if not data_rows_to_analyze:
            # Fallback to header row
            header_row = sorted(rows[header_row_idx], key=lambda i: i['x0'])
            return [item['x0'] for item in header_row], header_row_idx
        
        # Collect all X positions from data rows and cluster them
        all_x_positions = []
        for row in data_rows_to_analyze:
            for item in row:
                all_x_positions.append(item['x0'])
        
        # Sort and find clusters (column boundaries)
        all_x_positions.sort()
        
        if not all_x_positions:
            header_row = sorted(rows[header_row_idx], key=lambda i: i['x0'])
            return [item['x0'] for item in header_row], header_row_idx
        
        # Cluster X positions - items within 30px are same column
        column_boundaries = []
        current_cluster = [all_x_positions[0]]
        
        for x in all_x_positions[1:]:
            if x - current_cluster[-1] < 30:  # Same column
                current_cluster.append(x)
            else:  # New column
                # Use the minimum X of the cluster as the boundary
                column_boundaries.append(min(current_cluster))
                current_cluster = [x]
        
        # Add the last cluster
        if current_cluster:
            column_boundaries.append(min(current_cluster))
        
        logger.debug(f"Detected {len(column_boundaries)} column boundaries from data rows: {column_boundaries}")
        
        return column_boundaries, header_row_idx
    
    def _group_into_rows(self, items: List[Dict]) -> List[List[Dict]]:
        """Group text items into rows based on Y-coordinate proximity."""
        sorted_items = sorted(items, key=lambda i: i['y0'])
        rows = []
        
        if not sorted_items:
            return rows
        
        current_row = [sorted_items[0]]
        current_y = sorted_items[0]['y0']
        
        for item in sorted_items[1:]:
            if abs(item['y0'] - current_y) < 12:  # Threshold for row height
                current_row.append(item)
            else:
                rows.append(sorted(current_row, key=lambda i: i['x0']))
                current_row = [item]
                current_y = item['y0']
        
        rows.append(sorted(current_row, key=lambda i: i['x0']))
        return rows
    
    def _map_row_to_columns(self, row_items: List[Dict], boundaries: List[float]) -> List[str]:
        """
        Maps row items to columns based on X-coordinate boundaries.
        Returns a list of column values as strings.
        """
        if not boundaries:
            return []
        
        # Initialize columns
        col_data = [""] * max(5, len(boundaries))
        
        for item in row_items:
            # Find the column index by comparing X-coordinate to boundaries
            col_idx = 0
            for idx, b in enumerate(boundaries):
                if item['x0'] >= b - 10:  # 10px tolerance
                    col_idx = idx
            
            # Ensure we don't exceed array bounds
            if col_idx < len(col_data):
                col_data[col_idx] = f"{col_data[col_idx]} {item['text']}".strip()
        
        return col_data
    
    def _parse_structured_row(
        self, 
        row_items: List[Dict], 
        boundaries: List[float],
        page_num: int = 0,
        row_idx: int = 0
    ) -> tuple[Optional[Dict], bool]:
        """
        Maps text fragments to columns based on X-coordinates and applies Fill-Down logic.
        Expects 5 columns: STATE | BUSINESS UNIT | FEEDER NAME | BAND | CAP
        
        Returns: (feeder_dict, used_fallback)
        """
        if not boundaries or len(boundaries) < 4:
            return None, False
        
        # Map row items to columns
        col_data = self._map_row_to_columns(row_items, boundaries)
        
        # Debug: Show all column data with indices
        col_debug = " | ".join([f"[{i}]:'{col_data[i]}'" for i in range(min(7, len(col_data)))])
        logger.debug(f"Column data: {col_debug}")
        
        # Map columns based on expected structure
        # Column 0: STATE
        # Column 1: BUSINESS UNIT  
        # Column 2: FEEDER NAME
        # Column 3+: BAND and CAP (may be in any of the remaining columns)
        
        state = col_data[0].upper() if col_data[0] else self.last_state
        bu = col_data[1].upper() if len(col_data) > 1 and col_data[1] else self.last_bu
        feeder_name = col_data[2].upper() if len(col_data) > 2 else ""
        
        # Update persistence
        if col_data[0]:
            self.last_state = col_data[0].upper()
        if len(col_data) > 1 and col_data[1]:
            self.last_bu = col_data[1].upper()
        
        # Data Cleaning for Band and Cap - search across all remaining columns
        # Band is a single letter (A-E), Cap is a number
        band = ""
        cap = 0.0
        
        # Search each remaining column for band and cap
        for i in range(3, len(col_data)):
            col_text = col_data[i].strip()
            if not col_text:
                continue
            
            # Try to extract band from this column
            if not band:
                extracted_band = self._extract_band(col_text)
                if extracted_band:
                    band = extracted_band
                    logger.debug(f"Found band '{band}' in column {i}: '{col_text}'")
            
            # Try to extract cap from this column
            if cap == 0.0:
                extracted_cap = self._extract_cap(col_text)
                if extracted_cap > 0:
                    cap = extracted_cap
                    logger.debug(f"Found cap {cap} in column {i}: '{col_text}'")
        
        # If band still not found, check if OCR missed it - look at raw row items
        # Sometimes the band character is detected but placed in wrong column
        if not band:
            for item in row_items:
                text = item['text'].strip().upper()
                # Check if this is a standalone single letter A-E
                if len(text) == 1 and text in self.VALID_BANDS:
                    band = text
                    logger.debug(f"Found band '{band}' in raw row item: '{item['text']}' at x={item['x0']}")
                    break
        
        # Debug: Show raw band_cap_text with repr to see hidden characters
        all_remaining = " ".join(col_data[3:])
        logger.debug(f"All remaining columns: repr={repr(all_remaining)}, len={len(all_remaining)}")
        logger.debug(f"Extracted - band: '{band}', cap: {cap}")
        
        # Debug: Log the parsed columns
        row_text = " | ".join(col_data[:6])
        
        # Validation with debug logging
        if not feeder_name or len(feeder_name) < 3:
            logger.debug(f"Row rejected - feeder_name too short: '{feeder_name}' (len={len(feeder_name)}), row: {row_text}")
            return None, False
        
        # Fallback strategy for missing band
        used_fallback = False
        if not band:
            # Use "-" as fallback when band cannot be detected
            band = "-"
            used_fallback = True
            logger.warning(f"Band missing - using fallback '-' for feeder '{feeder_name}'")
        
        if band not in self.VALID_BANDS and band != "-":
            logger.debug(f"Row rejected - invalid band '{band}' not in {self.VALID_BANDS}, row: {row_text}")
            return None, False
        
        # Update last known band for tracking (but not for fallback anymore)
        if not used_fallback and band != "-":
            self.last_band = band
        
        logger.debug(f"Row accepted - state: {self.last_state}, bu: {self.last_bu}, feeder: {feeder_name}, band: {band}, cap: {cap}{' (FALLBACK)' if used_fallback else ''}")
        
        return {
            "state": self.last_state,
            "business_unit": self.last_bu,
            "name": feeder_name,
            "tariff_band": band,
            "cap_kwh": cap
        }, used_fallback
    
    def _get_rejection_info(
        self,
        row_items: List[Dict],
        boundaries: List[float],
        page_num: int,
        row_idx: int
    ) -> Optional[Dict]:
        """Extract information about a rejected row for reporting."""
        if not row_items:
            return None
        
        col_data = self._map_row_to_columns(row_items, boundaries)
        
        # Try to extract whatever we can
        state = col_data[0].upper() if col_data[0] else self.last_state or "UNKNOWN"
        bu = col_data[1].upper() if len(col_data) > 1 and col_data[1] else self.last_bu or "UNKNOWN"
        feeder_name = col_data[2].upper() if len(col_data) > 2 and col_data[2] else "UNKNOWN"
        
        # Get raw text for debugging
        raw_text = " | ".join([item['text'] for item in row_items])
        
        return {
            "page": page_num,
            "row": row_idx,
            "state": state,
            "business_unit": bu,
            "feeder_name": feeder_name if feeder_name != "UNKNOWN" else None,
            "raw_text": raw_text,
            "reason": "Missing required fields or invalid data"
        }
    
    def _extract_band(self, text: str) -> str:
        """Extract valid band letter (A-E) from text."""
        match = re.search(r'\b([A-Ea-e])\b', text.upper())
        return match.group(1) if match else ""
    
    def _extract_cap(self, text: str) -> float:
        """Extract numeric cap value from text."""
        clean = text.replace(",", "").replace("O", "0").replace("o", "0")
        nums = re.findall(r'\d+', clean)
        return float(max(nums, key=len)) if nums else 0.0


# Public API function
def parse_nerc_pdf(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Parse NERC PDF and extract feeder data.
    
    Args:
        pdf_bytes: PDF file content as bytes
        
    Returns:
        Dict with:
        - feeders: List of feeder dicts (state, business_unit, name, tariff_band, cap_kwh)
        - pages: List of page metadata (number, total_rows, rows_extracted)
    """
    parser = RavenPDFParser()
    try:
        return parser.parse(pdf_bytes)
    except Exception as e:
        logger.error(f"Error extracting data from PDF: {e}")
        raise
