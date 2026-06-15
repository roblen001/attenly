"""Database tables. How the data will be stored in the database."""
# models.py
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
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


class UserQuota(Base):
    __tablename__ = "user_quotas"

    user_id = Column(String, primary_key=True)
    monthly_limit_cad = Column(Numeric(10, 4), nullable=False)
    cost_used_cad = Column(Numeric(10, 6), nullable=False, default=0)
    billing_period_start = Column(Date, nullable=False)
    plan = Column(String(50), nullable=False, default="free")
    last_warning_level = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(String, nullable=False, index=True)
    operation_type = Column(String(80), nullable=False, index=True)
    model_name = Column(String(255), nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cost_cad = Column(Numeric(10, 6), nullable=False)
    usage_metadata = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    __table_args__ = (
        Index("idx_usage_logs_user_created", "user_id", "created_at"),
    )


class EmailIngestEndpoint(Base):
    __tablename__ = "email_ingest_endpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(String, nullable=False, unique=True, index=True)
    local_part = Column(String(255), nullable=False)
    domain = Column(String(255), nullable=False)
    full_address = Column(String(512), nullable=False, unique=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    default_agent_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    jobs = relationship(
        "EmailJob",
        back_populates="endpoint",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("local_part", "domain", name="unique_email_alias"),
    )


class VerifiedSender(Base):
    __tablename__ = "verified_senders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(String, nullable=False, index=True)
    email = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    verification_token = Column(String(255), nullable=True, index=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "email", name="unique_user_email"),
        Index("idx_verified_senders_email_status", "email", "status"),
    )


class EmailJob(Base):
    __tablename__ = "email_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(String, nullable=False, index=True)
    ingest_endpoint_id = Column(
        UUID(as_uuid=True),
        ForeignKey("email_ingest_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_email = Column(String(255), nullable=False)
    subject = Column(Text, nullable=True)
    instruction_text = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    report_id = Column(String, nullable=True)
    provider_message_id = Column(String(512), nullable=False, unique=True)
    raw_metadata = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    attachment_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    endpoint = relationship("EmailIngestEndpoint", back_populates="jobs")

    __table_args__ = (
        Index("idx_email_jobs_user_created", "user_id", "created_at"),
        Index("idx_email_jobs_status_created", "status", "created_at"),
    )


class EmailPollState(Base):
    __tablename__ = "email_poll_state"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider = Column(String(80), nullable=False)
    mailbox = Column(String(255), nullable=False)
    state_key = Column(String(255), nullable=False, default="default")
    delta_link = Column(Text, nullable=True)
    last_message_id = Column(String(512), nullable=True)
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)
    last_polled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    __table_args__ = (
        UniqueConstraint("provider", "mailbox", "state_key", name="unique_email_poll_state"),
    )
