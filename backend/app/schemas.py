"""Pydantic classes that define how data is sent/received in the API (how data is validated & returned)."""

# schemas.py
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import List, Optional
from uuid import UUID

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

class Agent(BaseAgentOut):
    """Schema for prebuilt agents loaded from JSON"""
    pass

class AgentOut(BaseAgentOut):
    """Schema for user-created agents from database"""
    id: UUID
    createdAt: datetime
    updatedAt: datetime

    model_config = ConfigDict(from_attributes=True)
