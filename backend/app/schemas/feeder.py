import uuid
from typing import Any, List, Optional

from pydantic import BaseModel

from app.models.feeder import TariffBand


class FeederSuggest(BaseModel):
    id: uuid.UUID
    name: str
    business_unit: Optional[str]
    formatted_address: Optional[str]
    tariff_band: TariffBand

    model_config = {"from_attributes": True}


class FeederDetails(BaseModel):
    id: uuid.UUID
    name: str
    business_unit: Optional[str]
    formatted_address: Optional[str]
    tariff_band: TariffBand
    state: Optional[str]
    longitude: Optional[float]
    latitude: Optional[float]
    cap_kwh: Optional[float]
    confidence_score: float
    aliases: Optional[Any]
    raven_score: Optional[float] = None

    model_config = {"from_attributes": True}


class CoordinateSearchIn(BaseModel):
    latitude: float
    longitude: float


class CoordinateSearchOut(BaseModel):
    feeder: Optional[FeederDetails]
    confidence: str  # HIGH | MEDIUM | LOW
