import uuid
from typing import List

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.disco import Disco
from app.models.feeder import Feeder, TariffBand
from app.models.user import User
from app.schemas.disco import BulkDiscoIn, DiscoOut, DiscoUpdate
from app.services.nerc import parse_nerc_pdf

router = APIRouter(prefix="/admin", tags=["admin"])


# ── NERC PDF ──────────────────────────────────────────────────────────────────

@router.post("/parse-nerc")
async def parse_nerc_upload(
    file: UploadFile = File(...),
    disco_id: uuid.UUID = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Upload a NERC PDF manually and parse feeders into the DB."""
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    if not disco_id:
        raise HTTPException(status_code=400, detail="disco_id query param is required")

    disco = await _get_disco_or_404(db, disco_id)
    content = await file.read()
    return await _parse_and_save(db, content, disco)


@router.post("/parse-nerc/{disco_id}/fetch")
async def parse_nerc_from_url(
    disco_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Fetch the PDF from the disco's stored path URL and parse feeders into the DB.
    The disco must have a valid URL in its `path` field.
    """
    disco = await _get_disco_or_404(db, disco_id)

    if not disco.path:
        raise HTTPException(status_code=400, detail="This DisCo has no PDF path configured")

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(disco.path)
            resp.raise_for_status()
            content = resp.content
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch PDF: {e}")

    return await _parse_and_save(db, content, disco)


# ── HELPERS ───────────────────────────────────────────────────────────────────

async def _get_disco_or_404(db: AsyncSession, disco_id: uuid.UUID) -> Disco:
    result = await db.execute(select(Disco).where(Disco.id == disco_id))
    disco = result.scalar_one_or_none()
    if not disco:
        raise HTTPException(status_code=404, detail="DisCo not found")
    return disco


async def _parse_and_save(db: AsyncSession, pdf_bytes: bytes, disco: Disco) -> dict:
    """Parse PDF bytes and upsert feeders into the DB for the given disco."""
    rows = parse_nerc_pdf(pdf_bytes)

    if not rows:
        return {"parsed": 0, "saved": 0, "message": "No feeder data found in PDF"}

    saved = 0
    skipped = 0

    for row in rows:
        try:
            band = TariffBand(row["tariff_band"])
        except ValueError:
            skipped += 1
            continue

        # Upsert by disco_id + name (avoid duplicates on re-parse)
        existing = await db.execute(
            select(Feeder).where(
                Feeder.disco_id == disco.id,
                Feeder.name == row["name"],
            )
        )
        feeder = existing.scalar_one_or_none()

        if feeder:
            # Update existing
            feeder.tariff_band = band
            feeder.business_unit = row.get("business_unit")
            feeder.state = row.get("state")
            feeder.cap_kwh = row.get("cap_kwh")
        else:
            feeder = Feeder(
                disco_id=disco.id,
                name=row["name"],
                tariff_band=band,
                business_unit=row.get("business_unit"),
                state=row.get("state"),
                cap_kwh=row.get("cap_kwh"),
            )
            db.add(feeder)

        saved += 1

    await db.commit()
    return {
        "parsed": len(rows),
        "saved": saved,
        "skipped": skipped,
        "disco": disco.name,
        "message": f"Successfully imported {saved} feeders for {disco.name}",
    }


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
        existing = await db.execute(select(Disco).where(Disco.code == item.code))
        if existing.scalar_one_or_none():
            continue
        disco = Disco(**item.model_dump())
        db.add(disco)
        created.append(disco)
    await db.commit()
    for d in created:
        await db.refresh(d)
    return created


@router.get("/discos", response_model=List[DiscoOut])
async def list_discos(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(select(Disco).order_by(Disco.name))
    return result.scalars().all()


@router.get("/discos/{disco_id}", response_model=DiscoOut)
async def get_disco(
    disco_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    return await _get_disco_or_404(db, disco_id)


@router.put("/discos/{disco_id}", response_model=DiscoOut)
async def update_disco(
    disco_id: uuid.UUID,
    payload: DiscoUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    disco = await _get_disco_or_404(db, disco_id)
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
    disco = await _get_disco_or_404(db, disco_id)
    await db.delete(disco)
    await db.commit()
