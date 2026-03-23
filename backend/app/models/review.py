import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Review(Base):
    __tablename__ = "ratings_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    feeder_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("feeders.id"), nullable=False)
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_hours: Mapped[float] = mapped_column(Float, nullable=False)  # 0–24
    review: Mapped[str] = mapped_column(String, nullable=True)
    questions: Mapped[dict] = mapped_column(JSONB, default=dict)
    upvotes: Mapped[int] = mapped_column(Integer, default=0)
    downvotes: Mapped[int] = mapped_column(Integer, default=0)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="reviews")
    feeder = relationship("Feeder", back_populates="reviews")
