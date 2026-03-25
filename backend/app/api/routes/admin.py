import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.disco import BulkDiscoIn, DiscoOut, DiscoUpdate
from app.services.disco import get_disco_by_id, get_disco_by_code, list_discos
from app.services.feeder_import import fetch_pdf_from_disco, parse_and_save_feeders
from app.models.disco import Disco
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


@router.get("/discos/{disco_id}", response_model=DiscoOut)
async def get_disco(
    disco_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    return await get_disco_by_id(db, disco_id)


@router.put("/discos/{disco_id}", response_model=DiscoOut)
async def update_disco(
    disco_id: uuid.UUID,
    payload: DiscoUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    disco = await get_disco_by_id(db, disco_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(disco, field, value)
    await db.commit()
    await db.refresh(disco)
    return disco


@router.delete("/discos/{disco_id}", status_code=204)
async def delete_disco(
    disco_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    disco = await get_disco_by_id(db, disco_id)
    await db.delete(disco)
    await db.commit()
