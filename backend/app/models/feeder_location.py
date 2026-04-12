import uuid

from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FeederLocation(Base):
    __tablename__ = "feeder_locations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feeder_name: Mapped[str] = mapped_column(String, nullable=False)
    disco_code: Mapped[str] = mapped_column(String(10), nullable=False)
    location_description: Mapped[str] = mapped_column(String, nullable=True)
    band: Mapped[str] = mapped_column(String(10), nullable=True)  # Tariff band from MYTO document

    streets = relationship("FeederStreet", back_populates="feeder_location", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_feeder_locations_disco", "disco_code"),
        Index("idx_feeder_locations_feeder", "feeder_name", "disco_code"),
    )


class FeederStreet(Base):
    __tablename__ = "feeder_streets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feeder_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feeder_locations.id", ondelete="CASCADE"), nullable=False
    )
    street_name: Mapped[str] = mapped_column(String, nullable=False)
    formatted_address: Mapped[str] = mapped_column(String, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    bounds = mapped_column(Geometry(geometry_type="POLYGON", srid=4326), nullable=True)

    feeder_location = relationship("FeederLocation", back_populates="streets")

    __table_args__ = (
        Index("idx_feeder_streets_location", "feeder_location_id"),
        Index("idx_feeder_streets_bounds", "bounds", postgresql_using="gist"),
    )
