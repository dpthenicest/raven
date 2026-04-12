"""MYTO import service — downloads, parses, and saves feeder location/street data."""
import re
import httpx
from loguru import logger
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, List, Optional

from app.models.feeder_location import FeederLocation, FeederStreet
from app.services.myto_parser import parse_myto_pdf
# from app.services.geocoding import GeocodingService  # ← uncomment to enable geocoding

_VALID_BAND = re.compile(r'[A-Ea-e]')


def _clean_band(raw: Optional[str]) -> Optional[str]:
    """
    Extract a single valid tariff band letter (A-E) from a raw string.
    Returns None if no valid letter is found.

    Examples:
        'DDDDDD' -> 'D'
        'Band A' -> 'A'
        'B '    -> 'B'
        'XYZ'   -> None
    """
    if not raw:
        return None
    match = _VALID_BAND.search(raw)
    return match.group(0).upper() if match else None


async def fetch_pdf(url: str) -> bytes:
    """Download a PDF from a URL and return its bytes."""
    logger.info(f"Downloading MYTO PDF from: {url}")
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        logger.info(f"Downloaded {len(resp.content):,} bytes from {url}")
        return resp.content


async def import_myto_for_disco(
    db: AsyncSession,
    disco_code: str,
    pdf_bytes: bytes,
    skip_pages: int = 0,
) -> Dict[str, Any]:
    """
    Parse MYTO PDF bytes and save feeder_locations + feeder_streets for a disco.

    Strategy:
    - Delete all existing feeder_locations (cascades to feeder_streets) for this disco
    - Insert all parsed entries — no restriction against the feeders table
    - feeder_name and disco_code are stored as-is for later joining with feeders table
    - Geocoding is prepared but disabled — enable after verifying stored data
    """
    logger.info(f"Starting MYTO import for disco: {disco_code}")

    parse_result = parse_myto_pdf(pdf_bytes, skip_pages=skip_pages)
    parsed_feeders = parse_result["feeders"]

    if not parsed_feeders:
        return {
            "disco_code": disco_code,
            "parsed": 0,
            "saved": 0,
            "skipped": 0,
            "message": "No feeder data found in MYTO PDF",
        }

    # Replace all existing data for this disco
    await db.execute(
        delete(FeederLocation).where(FeederLocation.disco_code == disco_code)
    )
    logger.info(f"Cleared existing feeder_locations for disco '{disco_code}'")

    saved = 0
    skipped = 0

    for entry in parsed_feeders:
        feeder_name = entry["feeder_name"].strip()
        location_desc = entry["location_description"]
        streets = entry["streets"]

        if not feeder_name:
            skipped += 1
            continue

        feeder_location = FeederLocation(
            feeder_name=feeder_name,
            disco_code=disco_code,
            location_description=location_desc,
            band=_clean_band(entry.get("band")),
        )
        db.add(feeder_location)
        await db.flush()  # get id before inserting streets

        for street_name in streets:
            street = FeederStreet(
                feeder_location_id=feeder_location.id,
                street_name=street_name,
                # formatted_address is left null — populated by geocoding
            )
            db.add(street)

        # ── GEOCODING (disabled — enable after verifying feeder_locations/streets) ──
        # geocoder = GeocodingService()
        # for street in feeder_location.streets:
        #     parts = [street.street_name]
        #     if location_desc:
        #         parts.append(location_desc)
        #     parts.append("Nigeria")
        #     address = ", ".join(parts)
        #     geo = await geocoder.geocode_address(address)
        #     if geo:
        #         street.latitude = geo["latitude"]
        #         street.longitude = geo["longitude"]
        #         street.formatted_address = geo.get("formatted_address")
        #         if geo.get("bounds"):
        #             street.bounds = GeocodingService.bounds_to_polygon(geo["bounds"])
        # ─────────────────────────────────────────────────────────────────────────────

        saved += 1
        logger.debug(f"Saved: '{feeder_name}' — {len(streets)} streets")

    await db.commit()

    logger.info(
        f"MYTO import complete for '{disco_code}': {saved} saved, {skipped} skipped"
    )

    return {
        "disco_code": disco_code,
        "parsed": parse_result["parsed"],
        "saved": saved,
        "skipped": skipped,
        "message": f"Imported {saved} feeder locations for {disco_code}",
    }


async def import_myto_batch(
    db: AsyncSession,
    entries: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    """Process an array of {disco_code, url} entries sequentially."""
    results = []
    for entry in entries:
        disco_code = entry["disco_code"]
        url = entry["url"]
        try:
            pdf_bytes = await fetch_pdf(url)
            result = await import_myto_for_disco(db, disco_code, pdf_bytes, entry.get("skip_pages", 0))
            results.append(result)
        except Exception as e:
            logger.error(
                f"Failed to import MYTO for disco '{disco_code}' from {url}: {e}",
                exc_info=True,
            )
            results.append({
                "disco_code": disco_code,
                "parsed": 0,
                "saved": 0,
                "skipped": 0,
                "error": str(e),
                "message": f"Import failed: {str(e)}",
            })
    return results
