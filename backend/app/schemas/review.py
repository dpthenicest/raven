import uuid
from typing import Any, Optional

from pydantic import BaseModel, field_validator


class ReviewIn(BaseModel):
    feeder_id: uuid.UUID
    stars: int
    actual_hours: float
    review: Optional[str] = None
    questions: Optional[Any] = None

    @field_validator("stars")
    @classmethod
    def validate_stars(cls, v):
        if not 1 <= v <= 5:
            raise ValueError("stars must be between 1 and 5")
        return v

    @field_validator("actual_hours")
    @classmethod
    def validate_hours(cls, v):
        if not 0 <= v <= 24:
            raise ValueError("actual_hours must be between 0 and 24")
        return v


class ReviewOut(BaseModel):
    id: uuid.UUID
    feeder_id: uuid.UUID
    stars: int
    actual_hours: float
    review: Optional[str]
    upvotes: int
    downvotes: int
    is_verified: bool

    model_config = {"from_attributes": True}
