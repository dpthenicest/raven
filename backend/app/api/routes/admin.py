import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.disco import BulkDiscoIn, DiscoOut, DiscoUpdate
from app.schemas.feeder import FeederCreate, FeederDetails, FeederUpdate
from app.services.disco import get_disco_by_id, get_disco_by_code, list_discos
from app.services.feeder_import import fetch_pdf_from_disco, parse_and_save_feeders
from app.services.geocoding import GeocodingService
from app.models.disco import Disco
from app.models.feeder import Feeder
from sqlalchemy import select

router = APIRouter(prefix="/admin", tags=["admin"])


# ── NERC PDF ──────────────────────────────────────────────────────────────────

@router.post("/parse-nerc")
async def parse_nerc_upload(
    disco_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Upload a NERC PDF and parse feeders into the DB for the given disco."""
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    # logger.info(f"NERC PDF upload for disco_id={disco_id}, file={file.filename}")
    disco = await get_disco_by_id(db, disco_id)
    content = await file.read()
    return await parse_and_save_feeders(db, content, disco)


@router.post("/parse-nerc/{disco_code}/fetch")
async def parse_nerc_from_url(
    disco_code: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Fetch the PDF from the disco's stored path URL and parse feeders into the DB."""
    # logger.info(f"NERC PDF fetch triggered for disco_code={disco_code}")
    disco = await get_disco_by_code(db, disco_code)
    if not disco:
        raise HTTPException(status_code=404, detail="DisCo not found")
    content = await fetch_pdf_from_disco(disco)
    return await parse_and_save_feeders(db, content, disco)


# ── DISCOS ────────────────────────────────────────────────────────────────────

@router.post("/discos", response_model=List[DiscoOut], status_code=201)
async def create_discos(
    payload: BulkDiscoIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Add one or more DisCos."""
    created = []
    for item in payload.discos:
        if await get_disco_by_code(db, item.code):
            logger.warning(f"Disco already exists, skipping: {item.code}")
            continue
        disco = Disco(**item.model_dump())
        db.add(disco)
        created.append(disco)
    await db.commit()
    for d in created:
        await db.refresh(d)
    logger.info(f"Created {len(created)} disco(s)")
    return created


@router.get("/discos", response_model=List[DiscoOut])
async def get_discos(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    return await list_discos(db)


@router.get("/discos/{disco_code}", response_model=DiscoOut)
async def get_disco(
    disco_code: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    disco = await get_disco_by_code(db, disco_code)
    if not disco:
        raise HTTPException(status_code=404, detail="DisCo not found")
    return disco


@router.put("/discos/{disco_code}", response_model=DiscoOut)
async def update_disco(
    disco_code: str,
    payload: DiscoUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    disco = await get_disco_by_code(db, disco_code)
    if not disco:
        raise HTTPException(status_code=404, detail="DisCo not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(disco, field, value)
    await db.commit()
    await db.refresh(disco)
    return disco


@router.delete("/discos/{disco_code}", status_code=204)
async def delete_disco(
    disco_code: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    disco = await get_disco_by_code(db, disco_code)
    if not disco:
        raise HTTPException(status_code=404, detail="DisCo not found")
    await db.delete(disco)
    await db.commit()


# ── FEEDERS ───────────────────────────────────────────────────────────────────

@router.post("/feeders", response_model=FeederDetails, status_code=201)
async def create_feeder(
    payload: FeederCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Manually create a new feeder entry."""
    # Verify disco exists
    disco = await get_disco_by_code(db, payload.disco_code)
    if not disco:
        raise HTTPException(status_code=404, detail=f"DisCo with code '{payload.disco_code}' not found")
    
    feeder = Feeder(**payload.model_dump())
    db.add(feeder)
    await db.commit()
    await db.refresh(feeder)
    logger.info(f"Manually created feeder: {feeder.name} ({feeder.id})")
    return feeder


@router.put("/feeders/{feeder_id}", response_model=FeederDetails)
async def update_feeder(
    feeder_id: uuid.UUID,
    payload: FeederUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Update feeder information (band, cap, location, etc.)."""
    result = await db.execute(select(Feeder).where(Feeder.id == feeder_id))
    feeder = result.scalar_one_or_none()
    
    if not feeder:
        raise HTTPException(status_code=404, detail="Feeder not found")
    
    # Update only provided fields
    update_data = payload.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(feeder, field, value)
    
    await db.commit()
    await db.refresh(feeder)
    logger.info(f"Updated feeder {feeder.name} ({feeder_id}): {list(update_data.keys())}")
    return feeder


@router.get("/feeders/{feeder_id}", response_model=FeederDetails)
async def get_feeder(
    feeder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Get feeder details by ID."""
    result = await db.execute(select(Feeder).where(Feeder.id == feeder_id))
    feeder = result.scalar_one_or_none()
    
    if not feeder:
        raise HTTPException(status_code=404, detail="Feeder not found")
    
    return feeder


# ── GEOCODING ─────────────────────────────────────────────────────────────────

@router.post("/geocode/all")
async def geocode_all_feeders(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Geocode all feeders using Google Maps API.
    
    This will update latitude, longitude, formatted_address, and bounds
    for all feeders in the database.
    """
    return await GeocodingService.geocode_all_feeders(db)


@router.post("/geocode/disco/{disco_code}")
async def geocode_feeders_by_disco(
    disco_code: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Geocode all feeders for a specific disco using Google Maps API.
    
    This will update latitude, longitude, formatted_address, and bounds
    for all feeders belonging to the specified disco.
    """
    # Verify disco exists
    disco = await get_disco_by_code(db, disco_code)
    if not disco:
        raise HTTPException(status_code=404, detail=f"DisCo with code '{disco_code}' not found")
    
    return await GeocodingService.geocode_feeders_by_disco(db, disco_code)


@router.post("/geocode/feeder/{feeder_id}")
async def geocode_single_feeder(
    feeder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Geocode a single feeder using Google Maps API.
    
    This will update latitude, longitude, formatted_address, and bounds
    for the specified feeder.
    """
    result = await db.execute(select(Feeder).where(Feeder.id == feeder_id))
    feeder = result.scalar_one_or_none()
    
    if not feeder:
        raise HTTPException(status_code=404, detail="Feeder not found")
    
    success = await GeocodingService.geocode_feeder(db, feeder)
    
    if not success:
        raise HTTPException(
            status_code=500, 
            detail="Failed to geocode feeder. Check logs for details."
        )
    
    await db.commit()
    await db.refresh(feeder)
    
    return {
        "feeder_id": feeder.id,
        "name": feeder.name,
        "latitude": feeder.latitude,
        "longitude": feeder.longitude,
        "formatted_address": feeder.formatted_address,
        "message": "Feeder geocoded successfully"
    }

