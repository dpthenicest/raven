import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SearchSource(str, PyEnum):
    LIST = "LIST"
    MAP = "MAP"


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    feeder_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("feeders.id"), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=True)
    lng: Mapped[float] = mapped_column(Float, nullable=True)
    found_band: Mapped[str] = mapped_column(String(1), nullable=True)
    device_type: Mapped[str] = mapped_column(String, nullable=True)
    search_source: Mapped[SearchSource] = mapped_column(Enum(SearchSource), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="searches")
    feeder = relationship("Feeder", back_populates="searches")

    __table_args__ = (Index("idx_searches_user_id", "user_id"),)
