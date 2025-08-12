"""Pydantic classes that define how data is sent/received in the API (how data is validated & returned)."""

# TODO may need to redo once auth properly se up at frontend
# schemas.py
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime


class UserCreate(BaseModel):
    email: EmailStr
    hashed_password: str = Field(min_length=8, max_length=128)

    # full_name: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # Pydantic v2 (ORM mode)

    id: str
    email: EmailStr
    # full_name: str | None = None
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
