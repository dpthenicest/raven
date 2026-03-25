import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, require_credits
from app.db.session import get_db
from app.models.user import User
from app.schemas.feeder import CoordinateSearchIn, CoordinateSearchOut, FeederDetails, FeederSuggest
from app.services.feeder import compute_raven_score, get_feeder_details, search_by_coordinate, suggest_feeders

router = APIRouter(prefix="/feeders", tags=["feeders"])


@router.get("/suggest", response_model=List[FeederSuggest])
async def suggest(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Free autocomplete search — no credit deduction."""
    logger.debug(f"Feeder suggest query: '{q}'")
    results = await suggest_feeders(db, q)
    logger.debug(f"Suggest returned {len(results)} results for '{q}'")
    return results


@router.get("/{feeder_id}/details", response_model=FeederDetails)
async def feeder_details(
    feeder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_credits),
):
    """Costs 1 credit."""
    logger.info(f"Feeder details requested: {feeder_id} by user {current_user.id}")
    feeder = await get_feeder_details(db, feeder_id)
    if not feeder:
        logger.warning(f"Feeder not found: {feeder_id}")
        raise HTTPException(status_code=404, detail="Feeder not found")

    current_user.credits -= 1
    await db.commit()
    logger.info(f"Credit deducted for user {current_user.id}, remaining: {current_user.credits}")

    raven_score = await compute_raven_score(db, feeder_id)
    result = FeederDetails.model_validate(feeder)
    result.raven_score = raven_score
    return result
