import uuid
from typing import List, Optional

from pydantic import BaseModel


class DiscoIn(BaseModel):
    name: str
    code: str
    path: Optional[str] = None


class DiscoUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    path: Optional[str] = None


class DiscoOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    path: Optional[str]

    model_config = {"from_attributes": True}


class BulkDiscoIn(BaseModel):
    discos: List[DiscoIn]
