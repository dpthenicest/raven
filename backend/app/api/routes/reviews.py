import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, require_admin
from app.db.session import get_db
from app.models.review import Review
from app.models.user import User
from app.schemas.review import ReviewIn, ReviewOut

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=ReviewOut, status_code=201)
async def create_review(
    payload: ReviewIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    logger.info(f"Review submitted by user {current_user.id} for feeder {payload.feeder_id}")
    review = Review(
        user_id=current_user.id,
        feeder_id=payload.feeder_id,
        stars=payload.stars,
        actual_hours=payload.actual_hours,
        review=payload.review,
        questions=payload.questions or {},
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


@router.get("/feeder/{feeder_id}", response_model=List[ReviewOut])
async def get_feeder_reviews(
    feeder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Get reviews for a specific feeder with pagination."""
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Review)
        .where(Review.feeder_id == feeder_id)
        .order_by(Review.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    return result.scalars().all()


@router.get("", response_model=List[ReviewOut])
async def get_all_reviews(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    feeder_id: Optional[uuid.UUID] = Query(None, description="Filter by feeder"),
    min_stars: Optional[int] = Query(None, ge=1, le=5, description="Minimum star rating"),
    max_stars: Optional[int] = Query(None, ge=1, le=5, description="Maximum star rating"),
    is_verified: Optional[bool] = Query(None, description="Filter by verification status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    Get all reviews (admin only) with optional filters and pagination.

    Filters:
    - feeder_id: only reviews for a specific feeder
    - min_stars / max_stars: star rating range
    - is_verified: only verified or unverified reviews
    - page / page_size: pagination
    """
    query = select(Review).order_by(Review.created_at.desc())

    if feeder_id:
        query = query.where(Review.feeder_id == feeder_id)
    if min_stars is not None:
        query = query.where(Review.stars >= min_stars)
    if max_stars is not None:
        query = query.where(Review.stars <= max_stars)
    if is_verified is not None:
        query = query.where(Review.is_verified == is_verified)

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    return result.scalars().all()
