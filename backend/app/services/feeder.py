import uuid
from typing import List, Optional

from geoalchemy2.functions import ST_Contains, ST_DWithin, ST_Point, ST_SetSRID
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.feeder import Feeder
from app.models.feeder_location import FeederLocation, FeederStreet
from app.models.review import Review


async def suggest_feeders(db: AsyncSession, q: str, limit: int = 10) -> List[Feeder]:
    """Full-text search on feeders using search_vector."""
    logger.debug(f"Full-text search for feeders: '{q}'")
    query = (
        select(Feeder)
        .where(Feeder.search_vector.op("@@")(func.plainto_tsquery("english", q)))
        .order_by(func.ts_rank(Feeder.search_vector, func.plainto_tsquery("english", q)).desc())
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


async def get_feeder_details(db: AsyncSession, feeder_id: uuid.UUID) -> Optional[Feeder]:
    """Get feeder by ID."""
    logger.debug(f"Fetching feeder details: {feeder_id}")
    result = await db.execute(select(Feeder).where(Feeder.id == feeder_id))
    return result.scalar_one_or_none()


async def _feeder_from_street(db: AsyncSession, street: FeederStreet) -> Optional[Feeder]:
    """Resolve FeederStreet → FeederLocation → Feeder via feeder_name + disco_code."""
    loc_result = await db.execute(
        select(FeederLocation).where(FeederLocation.id == street.feeder_location_id)
    )
    location = loc_result.scalar_one_or_none()
    if not location:
        return None
    feeder_result = await db.execute(
        select(Feeder).where(
            Feeder.name == location.feeder_name,
            Feeder.disco_code == location.disco_code,
        )
    )
    return feeder_result.scalar_one_or_none()


async def search_by_coordinate(
    db: AsyncSession, lat: float, lng: float
) -> tuple[Optional[Feeder], str]:
    """
    Geospatial search using feeder_streets bounds.
    Tries exact polygon match (HIGH), then proximity (MEDIUM).
    """
    logger.info(f"Geospatial search: lat={lat}, lng={lng}")
    point = ST_SetSRID(ST_Point(lng, lat), 4326)

    result = await db.execute(
        select(FeederStreet).where(ST_Contains(FeederStreet.bounds, point)).limit(1)
    )
    street = result.scalar_one_or_none()
    if street:
        feeder = await _feeder_from_street(db, street)
        if feeder:
            logger.info(f"Exact polygon match: {feeder.name}")
            return feeder, "HIGH"

    result = await db.execute(
        select(FeederStreet).where(ST_DWithin(FeederStreet.bounds, point, 0.05)).limit(1)
    )
    street = result.scalar_one_or_none()
    if street:
        feeder = await _feeder_from_street(db, street)
        if feeder:
            logger.info(f"Near match: {feeder.name}")
            return feeder, "MEDIUM"

    logger.warning(f"No feeder found near lat={lat}, lng={lng}")
    return None, "LOW"


async def compute_raven_score(db: AsyncSession, feeder_id: uuid.UUID) -> Optional[float]:
    logger.debug(f"Computing Raven score for feeder: {feeder_id}")
    result = await db.execute(
        select(func.avg(Review.actual_hours)).where(Review.feeder_id == feeder_id)
    )
    return result.scalar_one_or_none()
