"""Pydantic classes that define how data is sent/received in the API (how data is validated & returned)."""
# schemas.py
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # Pydantic v2 (ORM mode)

    id: str
    email: EmailStr
    full_name: str | None = None
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime

class QuestionOut(BaseModel):
    id: str
    placeholder: str
    prompt: str

    model_config = ConfigDict(from_attributes=True)

class BaseAgentOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    reportTemplate: str  
    questions: List[QuestionOut] = []

    model_config = ConfigDict(from_attributes=True)

class PrebuiltAgentOut(BaseAgentOut):
    """Schema for prebuilt agents loaded from JSON"""
    pass

class AgentOut(BaseAgentOut):
    """Schema for user-created agents from database"""
    id: UUID
    createdAt: datetime
    updatedAt: datetime

    model_config = ConfigDict(from_attributes=True)
