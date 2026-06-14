"""Database tables. How the data will be stored in the database."""
# models.py
from sqlalchemy import Column, String, DateTime, Text, UniqueConstraint, ForeignKey, Boolean, Integer, JSON
from datetime import datetime, timezone
from uuid import uuid4
from .db import Base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

def utcnow():
    return datetime.now(timezone.utc)

class Agent(Base):
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    # The report template HTML
    report_template = Column(Text, nullable=True)
    
    # CSS styling for the report template (nullable for backward compatibility)
    report_template_css = Column(Text, nullable=True)
    
    # Custom agent fields
    user_id = Column(String, nullable=True)  # Links custom agents to their creators (nullable for prebuilt agents)
    is_custom = Column(Boolean, nullable=False, default=False)  # Distinguishes custom from prebuilt agents
    created_by_name = Column(String, nullable=True)  # User's display name for agent attribution
    
    # For user-created agents
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    questions = relationship(
        "AgentQuestion",
        back_populates="agent",
        cascade="all, delete-orphan",
    )

class AgentQuestion(Base):
    __tablename__ = "agent_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)

    placeholder = Column(String, nullable=False)
    prompt = Column(Text, nullable=False)

    agent = relationship("Agent", back_populates="questions")

    __table_args__ = (
        # Each placeholder should be unique per agent
        UniqueConstraint("agent_id", "placeholder", name="uq_agent_placeholder_per_agent"),
    )


class SavedReport(Base):
    __tablename__ = "saved_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(String, nullable=False, index=True)
    agent_id = Column(String, nullable=False)
    agent_name = Column(Text, nullable=False)
    report_name = Column(Text, nullable=False)
    report_data = Column(JSON, nullable=False)
    ai_baseline_answers = Column(JSON, nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    saved_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    documents = relationship(
        "SavedReportDocument",
        back_populates="report",
        cascade="all, delete-orphan",
    )
    changes = relationship(
        "ReportChange",
        back_populates="report",
        cascade="all, delete-orphan",
    )


class SavedReportDocument(Base):
    __tablename__ = "saved_report_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    report_id = Column(UUID(as_uuid=True), ForeignKey("saved_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(String, nullable=False)
    filename = Column(Text, nullable=False)
    document_metadata = Column("metadata", JSON, nullable=False, default=dict)
    storage_path = Column(Text, nullable=True)
    content_hash = Column(String, nullable=True)
    storage_bucket = Column(String, nullable=True)
    stored_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    report = relationship("SavedReport", back_populates="documents")

    __table_args__ = (
        UniqueConstraint("report_id", "document_id", name="uq_saved_report_document_per_report"),
    )


class ReportChange(Base):
    __tablename__ = "report_changes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    report_id = Column(UUID(as_uuid=True), ForeignKey("saved_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    answer_placeholder = Column(String(255), nullable=False, index=True)
    change_type = Column(String(10), nullable=False)
    text_content = Column(Text, nullable=False)
    start_offset = Column(Integer, nullable=False)
    end_offset = Column(Integer, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    user_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    report = relationship("SavedReport", back_populates="changes")
