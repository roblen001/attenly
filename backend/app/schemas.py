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

# Custom agent schemas
class CustomAgentOut(AgentOut):
    """Schema for custom agents with additional fields"""
    user_id: str
    is_custom: bool
    created_by_name: Optional[str] = None
    can_delete: bool = True  # Frontend computed property

    model_config = ConfigDict(from_attributes=True)

class CreateCustomAgentRequest(BaseModel):
    name: str
    description: Optional[str] = None
    report_template: str
    questions: List[QuestionOut]  # Use existing QuestionOut schema

class UpdateCustomAgentRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    report_template: Optional[str] = None
    questions: Optional[List[QuestionOut]] = None  # Use existing QuestionOut schema

# Schemas for saved reports functionality
class SaveReportRequest(BaseModel):
    report_name: str

class SavedReportOut(BaseModel):
    id: str
    report_name: str
    agent_name: str
    agent_id: str
    saved_at: datetime
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class SavedReportDetailOut(BaseModel):
    id: str
    report_name: str
    agent_name: str
    agent_id: str
    report_data: dict  # Complete ReportData structure
    saved_at: datetime
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Update payloads
class UpdateSavedReportRequest(BaseModel):
    report_data: Optional[dict] = None
    report_name: Optional[str] = None

# for now there is no save as options when updating cached reports (from saved reports)
class UpdateCachedReportRequest(BaseModel):
    report_data: dict
