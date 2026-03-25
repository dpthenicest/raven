import uuid
from datetime import datetime
from enum import Enum as PyEnum

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

from app.db.base import Base


class TariffBand(str, PyEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


class TSVector(UserDefinedType):
    """Custom type for PostgreSQL tsvector."""
    cache_ok = True

    def get_col_spec(self, **kw):
        return "TSVECTOR"


class Feeder(Base):
    __tablename__ = "feeders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    disco_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("discos.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    business_unit: Mapped[str] = mapped_column(String, nullable=True)
    tariff_band: Mapped[TariffBand] = mapped_column(Enum(TariffBand), nullable=False)
    formatted_address: Mapped[str] = mapped_column(String, nullable=True)
    aliases: Mapped[dict] = mapped_column(JSONB, default=list)
    state: Mapped[str] = mapped_column(String, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    bounds = mapped_column(Geometry(geometry_type="POLYGON", srid=4326), nullable=True)
    search_vector = mapped_column(TSVector, nullable=True)
    cap_kwh: Mapped[float] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    disco = relationship("Disco", back_populates="feeders")
    searches = relationship("Search", back_populates="feeder")
    reviews = relationship("Review", back_populates="feeder")

    __table_args__ = (
        Index("idx_feeders_search", "search_vector", postgresql_using="gin"),
        Index("idx_feeders_bounds", "bounds", postgresql_using="gist"),
        Index("idx_feeders_name", "name"),
    )
