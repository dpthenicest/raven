from typing import Any, Dict, List, Optional
from pydantic import BaseModel, HttpUrl


class MYTOImportEntry(BaseModel):
    """A single disco MYTO PDF to import."""
    disco_code: str
    url: str
    skip_pages: int = 0  # Number of pages to skip from the start of the PDF


class MYTOImportRequest(BaseModel):
    """Request body for batch MYTO import."""
    entries: List[MYTOImportEntry]


class MYTOImportResult(BaseModel):
    """Result for a single disco MYTO import."""
    disco_code: str
    parsed: int
    saved: int
    skipped: int
    unmatched: List[str] = []
    error: Optional[str] = None
    message: str


class FeederStreetOut(BaseModel):
    id: Any
    street_name: str
    formatted_address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]

    model_config = {"from_attributes": True}


class FeederLocationOut(BaseModel):
    id: Any
    feeder_name: str
    disco_code: str
    location_description: Optional[str]
    band: Optional[str]
    streets: List[FeederStreetOut] = []

    model_config = {"from_attributes": True}
