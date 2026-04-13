import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.myto import FeederLocationOut, MYTOImportRequest, MYTOImportResult
from app.services.geocoding import GeocodingService, geocode_address, bounds_to_polygon
from app.services.myto_import import import_myto_batch
from app.models.feeder_location import FeederLocation, FeederStreet
from sqlalchemy import select
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/admin", tags=["admin"])


# ── NERC PDF (disabled) ───────────────────────────────────────────────────────

# @router.post("/parse-nerc")
# async def parse_nerc_upload(
#     disco_id: uuid.UUID,
#     file: UploadFile = File(...),
#     db: AsyncSession = Depends(get_db),
#     _: User = Depends(require_admin),
# ):
#     if file.content_type != "application/pdf":
#         raise HTTPException(status_code=400, detail="Only PDF files are accepted")
#     from app.services.disco import get_disco_by_id
#     from app.services.feeder_import import parse_and_save_feeders
#     disco = await get_disco_by_id(db, disco_id)
#     content = await file.read()
#     return await parse_and_save_feeders(db, content, disco)


# @router.post("/parse-nerc/{disco_code}/fetch")
# async def parse_nerc_from_url(
#     disco_code: str,
#     db: AsyncSession = Depends(get_db),
#     _: User = Depends(require_admin),
# ):
#     from app.services.disco import get_disco_by_code
#     from app.services.feeder_import import fetch_pdf_from_disco, parse_and_save_feeders
#     disco = await get_disco_by_code(db, disco_code)
#     if not disco:
#         raise HTTPException(status_code=404, detail="DisCo not found")
#     content = await fetch_pdf_from_disco(disco)
#     return await parse_and_save_feeders(db, content, disco)


# ── DISCOS (disabled) ─────────────────────────────────────────────────────────

# @router.post("/discos", ...)
# @router.get("/discos", ...)
# @router.get("/discos/{disco_code}", ...)
# @router.put("/discos/{disco_code}", ...)
# @router.delete("/discos/{disco_code}", ...)


# ── FEEDERS (disabled) ────────────────────────────────────────────────────────

# @router.post("/feeders", ...)
# @router.put("/feeders/{feeder_id}", ...)
# @router.get("/feeders/{feeder_id}", ...)


# ── GEOCODING (disabled) ──────────────────────────────────────────────────────

# @router.post("/geocode/all", ...)
# @router.post("/geocode/disco/{disco_code}", ...)
# @router.post("/geocode/feeder/{feeder_id}", ...)


# ── MYTO ──────────────────────────────────────────────────────────────────────

@router.post("/myto/import", response_model=List[MYTOImportResult])
async def import_myto_pdfs(
    payload: MYTOImportRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Download and import MYTO PDFs for one or more discos.

    Example request:
    {
        "entries": [
            {"disco_code": "PHEDC", "url": "https://...", "skip_pages": 10},
            {"disco_code": "AEDC",  "url": "https://...", "skip_pages": 8}
        ]
    }
    """
    if not payload.entries:
        raise HTTPException(status_code=400, detail="No entries provided")
    return await import_myto_batch(db, [e.model_dump() for e in payload.entries])


@router.get("/myto/{disco_code}/locations", response_model=List[FeederLocationOut])
async def get_feeder_locations(
    disco_code: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Get all feeder locations (with streets) for a disco.
    Uses feeder_locations table directly.
    """
    result = await db.execute(
        select(FeederLocation)
        .where(FeederLocation.disco_code == disco_code)
        .options(selectinload(FeederLocation.streets))
        .order_by(FeederLocation.feeder_name)
    )
    locations = result.scalars().all()

    if not locations:
        raise HTTPException(
            status_code=404,
            detail=f"No feeder locations found for disco '{disco_code}'"
        )
    return locations


@router.post("/myto/{disco_code}/geocode")
async def geocode_feeder_streets_by_disco(
    disco_code: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Geocode all feeder streets for a specific disco.
    Builds address as: street_name, location_description, Nigeria.
    """
    result = await db.execute(
        select(FeederLocation)
        .where(FeederLocation.disco_code == disco_code)
        .options(selectinload(FeederLocation.streets))
    )
    locations = result.scalars().all()

    if not locations:
        raise HTTPException(
            status_code=404,
            detail=f"No feeder locations found for disco '{disco_code}'. Run MYTO import first."
        )

    total_streets = 0
    geocoded = 0
    failed = 0

    for location in locations:
        for street in location.streets:
            total_streets += 1

            geo = await geocode_address(street.street_name, location.location_description or "")
            if geo:
                street.latitude = geo["latitude"]
                street.longitude = geo["longitude"]
                street.formatted_address = geo.get("formatted_address")
                if geo.get("bounds"):
                    street.bounds = bounds_to_polygon(geo["bounds"])
                geocoded += 1
                logger.debug(f"Geocoded [{geo['source']}]: {street.street_name} → {street.latitude}, {street.longitude}")
            else:
                failed += 1
                logger.warning(f"Failed to geocode: {street.street_name}, {location.location_description}")

    await db.commit()
    return {
        "disco_code": disco_code,
        "total_streets": total_streets,
        "geocoded": geocoded,
        "failed": failed,
        "message": f"Geocoded {geocoded} of {total_streets} streets for {disco_code}",
    }


@router.post("/myto/geocode/all")
async def geocode_all_feeder_streets(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    force: bool = False,
):
    """
    Geocode ALL feeder streets across all discos.
    By default only processes streets where latitude is null.
    Pass ?force=true to re-geocode all streets including already geocoded ones.
    """
    query = (
        select(FeederStreet)
        .join(FeederLocation, FeederStreet.feeder_location_id == FeederLocation.id)
    )
    if not force:
        query = query.where(FeederStreet.latitude.is_(None))
    result = await db.execute(query)
    streets = result.scalars().all()

    if not streets:
        return {"total_streets": 0, "geocoded": 0, "failed": 0, "message": "No ungeocoded streets found"}

    location_ids = list({s.feeder_location_id for s in streets})
    loc_result = await db.execute(
        select(FeederLocation).where(FeederLocation.id.in_(location_ids))
    )
    location_map = {loc.id: loc for loc in loc_result.scalars().all()}

    total_streets = len(streets)
    geocoded = 0
    failed = 0

    for street in streets:
        location = location_map.get(street.feeder_location_id)

        geo = await geocode_address(street.street_name, location.location_description or "" if location else "")
        if geo:
            street.latitude = geo["latitude"]
            street.longitude = geo["longitude"]
            street.formatted_address = geo.get("formatted_address")
            if geo.get("bounds"):
                street.bounds = bounds_to_polygon(geo["bounds"])
            geocoded += 1
            logger.debug(f"Geocoded [{geo['source']}]: {street.street_name} → {street.latitude}, {street.longitude}")
        else:
            failed += 1
            logger.warning(f"Failed to geocode: {street.street_name}")

    await db.commit()
    return {
        "total_streets": total_streets,
        "geocoded": geocoded,
        "failed": failed,
        "message": f"Geocoded {geocoded} of {total_streets} streets across all discos",
    }
