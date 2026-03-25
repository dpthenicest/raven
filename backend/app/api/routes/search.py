from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_credits
from app.db.session import get_db
from app.models.search import Search, SearchSource
from app.models.user import User
from app.schemas.feeder import CoordinateSearchIn, CoordinateSearchOut, FeederDetails
from app.services.feeder import compute_raven_score, search_by_coordinate

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/coordinate", response_model=CoordinateSearchOut)
async def coordinate_search(
    payload: CoordinateSearchIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_credits),
):
    """Map-based search. Costs 1 credit."""
    logger.info(f"Coordinate search by user {current_user.id}: lat={payload.latitude}, lng={payload.longitude}")
    feeder, confidence = await search_by_coordinate(db, payload.latitude, payload.longitude)

    current_user.credits -= 1
    search_log = Search(
        user_id=current_user.id,
        feeder_id=feeder.id if feeder else None,
        lat=payload.latitude,
        lng=payload.longitude,
        found_band=feeder.tariff_band.value if feeder else None,
        search_source=SearchSource.MAP,
    )
    db.add(search_log)
    await db.commit()
    logger.info(f"Coordinate search result: feeder={feeder.name if feeder else None}, confidence={confidence}")

    if not feeder:
        return CoordinateSearchOut(feeder=None, confidence=confidence)

    raven_score = await compute_raven_score(db, feeder.id)
    feeder_out = FeederDetails.model_validate(feeder)
    feeder_out.raven_score = raven_score
    return CoordinateSearchOut(feeder=feeder_out, confidence=confidence)
