"""Disco service — DB helpers for DisCo operations."""
import uuid
from typing import List, Optional

from fastapi import HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.disco import Disco


async def get_disco_by_id(db: AsyncSession, disco_id: uuid.UUID) -> Disco:
    logger.debug(f"Fetching disco by id: {disco_id}")
    result = await db.execute(select(Disco).where(Disco.id == disco_id))
    disco = result.scalar_one_or_none()
    if not disco:
        logger.warning(f"Disco not found: {disco_id}")
        raise HTTPException(status_code=404, detail="DisCo not found")
    return disco


async def get_disco_by_code(db: AsyncSession, code: str) -> Optional[Disco]:
    # logger.debug(f"Fetching disco by code: {code}")
    result = await db.execute(select(Disco).where(Disco.code == code))
    return result.scalar_one_or_none()


async def list_discos(db: AsyncSession) -> List[Disco]:
    logger.debug("Listing all discos")
    result = await db.execute(select(Disco).order_by(Disco.name))
    return result.scalars().all()
