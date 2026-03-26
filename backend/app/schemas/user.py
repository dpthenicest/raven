import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from app.models.user import UserRole


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: Optional[str]
    credits: int
    role: UserRole
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        if not v:
            raise ValueError('Email is required')
        
        # Basic email regex pattern
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError('Invalid email format')
        
        return v.lower()


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
