"""Database tables. How the data will be stored in the database."""
# models.py
from sqlalchemy import Column, String, Boolean, DateTime, Text, ARRAY, UniqueConstraint, ForeignKey
from datetime import datetime, timezone
from uuid import uuid4
from .db import Base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

def utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)      
    email = Column(String, nullable=False, index=True)      
    full_name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    is_verified = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

class Agent(Base):
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    # The report template HTML
    report_template = Column(Text, nullable=True)
    
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
