import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
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
):
    result = await db.execute(
        select(Review).where(Review.feeder_id == feeder_id).order_by(Review.created_at.desc())
    )
    return result.scalars().all()
