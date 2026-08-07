"""Database tables. How the data will be stored in the database."""
# models.py
from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
    Uuid as UUID,
)
from datetime import datetime, timezone
from uuid import uuid4
from .db import Base
from sqlalchemy.orm import relationship

def utcnow():
    return datetime.now(timezone.utc)


class Organization(Base):
    """An enterprise boundary for members and organization-shared agents."""

    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    memberships = relationship(
        "OrganizationMembership",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    agents = relationship("Agent", back_populates="organization")
    sessions = relationship(
        "AppSession",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'blocked')",
            name="ck_organization_status",
        ),
    )


class AppUser(Base):
    """An Attenly user independent of any particular identity provider.

    ``resource_owner_id`` deliberately remains a string because existing private
    resources use string ``user_id`` columns. Authentication principals should
    continue passing this value to those existing ownership filters.
    """

    __tablename__ = "app_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    resource_owner_id = Column(String(255), nullable=False, unique=True, index=True)
    email = Column(String(320), nullable=True)
    display_name = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="active")
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    identities = relationship(
        "AuthIdentity",
        back_populates="app_user",
        cascade="all, delete-orphan",
    )
    memberships = relationship(
        "OrganizationMembership",
        back_populates="app_user",
        cascade="all, delete-orphan",
        foreign_keys="OrganizationMembership.app_user_id",
    )
    sessions = relationship(
        "AppSession",
        back_populates="app_user",
        cascade="all, delete-orphan",
    )
    created_agents = relationship(
        "Agent",
        back_populates="created_by_user",
        foreign_keys="Agent.created_by_user_id",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'blocked')",
            name="ck_app_user_status",
        ),
    )


class AuthIdentity(Base):
    """A verified external identity bound to an internal user."""

    __tablename__ = "auth_identities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    app_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider = Column(String(80), nullable=False)
    issuer = Column(String(2048), nullable=False)
    subject = Column(String(512), nullable=False)
    tenant_id = Column(String(255), nullable=True)
    object_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    app_user = relationship("AppUser", back_populates="identities")

    __table_args__ = (
        UniqueConstraint(
            "issuer",
            "subject",
            name="uq_auth_identity_issuer_subject",
        ),
        UniqueConstraint(
            "provider",
            "tenant_id",
            "object_id",
            name="uq_auth_identity_provider_tenant_object",
        ),
        CheckConstraint(
            "(tenant_id IS NULL AND object_id IS NULL) OR "
            "(tenant_id IS NOT NULL AND object_id IS NOT NULL)",
            name="ck_auth_identity_tenant_object_pair",
        ),
    )


class OrganizationMembership(Base):
    """A user's role and locally enforced access status within an organization."""

    __tablename__ = "organization_memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    app_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(32), nullable=False, default="user")
    status = Column(String(32), nullable=False, default="active")
    blocked_at = Column(DateTime(timezone=True), nullable=True)
    blocked_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    block_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    organization = relationship("Organization", back_populates="memberships")
    app_user = relationship(
        "AppUser",
        back_populates="memberships",
        foreign_keys=[app_user_id],
    )
    blocked_by_user = relationship("AppUser", foreign_keys=[blocked_by_user_id])

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "app_user_id",
            name="uq_organization_membership_user",
        ),
        CheckConstraint(
            "role IN ('user', 'admin')",
            name="ck_organization_membership_role",
        ),
        CheckConstraint(
            "status IN ('active', 'blocked')",
            name="ck_organization_membership_status",
        ),
        Index(
            "idx_organization_memberships_org_status",
            "organization_id",
            "status",
        ),
    )


class AppSession(Base):
    """An opaque browser session; only a one-way token hash is persisted."""

    __tablename__ = "app_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    app_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    revoked_reason = Column(String(255), nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)

    app_user = relationship("AppUser", back_populates="sessions")
    organization = relationship("Organization", back_populates="sessions")

    __table_args__ = (
        Index(
            "idx_app_sessions_user_org_active",
            "app_user_id",
            "organization_id",
            "revoked_at",
        ),
    )


class OIDCLoginTransaction(Base):
    """Short-lived server-side state for Authorization Code + PKCE logins."""

    __tablename__ = "oidc_login_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider = Column(String(80), nullable=False, default="oidc")
    state_hash = Column(String(64), nullable=False, unique=True, index=True)
    browser_binding_hash = Column(String(64), nullable=False)
    nonce = Column(String(255), nullable=False)
    code_verifier = Column(Text, nullable=False)
    redirect_uri = Column(Text, nullable=False)
    return_to = Column(Text, nullable=False, default="/")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)


class SecurityAuditEvent(Base):
    """An append-only record of security-relevant identity actions."""

    __tablename__ = "security_audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type = Column(String(100), nullable=False, index=True)
    outcome = Column(String(32), nullable=False, default="success")
    event_metadata = Column("metadata", JSON, nullable=False, default=dict)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)


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
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
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
    organization = relationship("Organization", back_populates="agents")
    created_by_user = relationship(
        "AppUser",
        back_populates="created_agents",
        foreign_keys=[created_by_user_id],
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
