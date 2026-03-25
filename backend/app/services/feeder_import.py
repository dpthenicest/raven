"""Feeder import service — parses NERC PDF bytes and upserts feeders into the DB."""
import httpx
from fastapi import HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.disco import Disco
from app.models.feeder import Feeder, TariffBand
from app.services.nerc import parse_nerc_pdf


async def fetch_pdf_from_disco(disco: Disco) -> bytes:
    """
    Download the PDF from the disco's stored path URL.
    
    Args:
        disco: Disco model instance with path URL
        
    Returns:
        PDF content as bytes
        
    Raises:
        HTTPException: If PDF path is missing or download fails
    """
    if not disco.path:
        raise HTTPException(
            status_code=400, 
            detail=f"DisCo '{disco.name}' ({disco.code}) has no PDF path configured"
        )
    
    logger.info(f"Fetching PDF for '{disco.name}' ({disco.code}) from: {disco.path}")
    
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(disco.path)
            resp.raise_for_status()
            
            content_length = len(resp.content)
            logger.info(f"PDF fetched successfully for '{disco.name}': {content_length:,} bytes")
            
            return resp.content
            
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch PDF for '{disco.name}' ({disco.code}): {e}")
        raise HTTPException(
            status_code=502, 
            detail=f"Failed to fetch PDF from {disco.path}: {str(e)}"
        )


async def parse_and_save_feeders(db: AsyncSession, pdf_bytes: bytes, disco: Disco) -> dict:
    """
    Parse PDF bytes and upsert feeders into the DB for the given disco.
    
    Args:
        db: Database session
        pdf_bytes: PDF file content
        disco: Disco model instance
        
    Returns:
        Dictionary with import statistics:
        - parsed: Number of rows parsed from PDF
        - saved: Number of feeders saved/updated
        - skipped: Number of rows skipped due to validation errors
        - pages: List of page statistics with number, rows, extracted, skipped per page
        - disco: Disco name
        - message: Summary message
    """
    logger.info(f"Starting feeder import for '{disco.name}' ({disco.code})")
    
    # Parse PDF
    try:
        rows, page_stats = parse_nerc_pdf(pdf_bytes)
    except Exception as e:
        logger.error(f"PDF parsing failed for '{disco.name}': {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse PDF: {str(e)}"
        )

    if not rows:
        logger.warning(f"No feeder data found in PDF for '{disco.name}'")
        return {
            "parsed": 0,
            "saved": 0,
            "skipped": 0,
            "pages": page_stats,
            "disco": disco.name,
            "message": "No feeder data found in PDF"
        }

    logger.info(f"Parsed {len(rows)} feeder rows from {len(page_stats)} pages for '{disco.name}'")
    
    # Process and save feeders
    saved = 0
    skipped = 0
    errors = []

    for idx, row in enumerate(rows):
        try:
            # Validate tariff band
            try:
                band = TariffBand(row["tariff_band"])
            except ValueError:
                logger.warning(
                    f"Row {idx + 1}: Invalid tariff band '{row.get('tariff_band')}' "
                    f"for feeder '{row.get('name')}' — skipping"
                )
                skipped += 1
                errors.append(f"Row {idx + 1}: Invalid band '{row.get('tariff_band')}'")
                continue

            # Check if feeder exists
            existing = await db.execute(
                select(Feeder).where(
                    Feeder.disco_code == disco.code,
                    Feeder.name == row["name"],
                )
            )
            feeder = existing.scalar_one_or_none()

            if feeder:
                # Update existing feeder
                logger.debug(f"Updating feeder: {feeder.name}")
                feeder.tariff_band = band
                feeder.business_unit = row.get("business_unit")
                feeder.state = row.get("state")
                feeder.cap_kwh = row.get("cap_kwh")
                feeder.formatted_address = row.get("formatted_address")
            else:
                # Create new feeder
                logger.debug(f"Creating new feeder: {row['name']}")
                feeder = Feeder(
                    disco_code=disco.code,
                    name=row["name"],
                    tariff_band=band,
                    business_unit=row.get("business_unit"),
                    state=row.get("state"),
                    cap_kwh=row.get("cap_kwh"),
                    formatted_address=row.get("formatted_address"),
                )
                db.add(feeder)

            saved += 1

        except Exception as e:
            logger.error(f"Error processing row {idx + 1}: {e}", exc_info=True)
            skipped += 1
            errors.append(f"Row {idx + 1}: {str(e)}")

    # Commit changes
    try:
        await db.commit()
        logger.info(
            f"Import complete for '{disco.name}': "
            f"{saved} saved, {skipped} skipped from {len(rows)} parsed rows"
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Database commit failed for '{disco.name}': {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save feeders to database: {str(e)}"
        )

    result = {
        "parsed": len(rows),
        "saved": saved,
        "skipped": skipped,
        "pages": page_stats,
        "disco": disco.name,
        "message": f"Successfully imported {saved} feeders for {disco.name}",
    }
    
    if errors and len(errors) <= 10:
        result["errors"] = errors
    elif errors:
        result["errors"] = errors[:10] + [f"... and {len(errors) - 10} more errors"]
    
    return result
