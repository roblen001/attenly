"""Identity-domain persistence for organization users and opaque sessions.

OIDC protocol validation belongs at the authentication boundary. This module
only accepts identities whose issuer, subject, and claims have already been
verified by that boundary, then maps them to Attenly's provider-neutral users.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import hmac
import secrets
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    AppSession,
    AppUser,
    AuthIdentity,
    OIDCLoginTransaction,
    Organization,
    OrganizationMembership,
    SecurityAuditEvent,
    utcnow,
)


class OrganizationRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class AccessStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class IdentityServiceError(Exception):
    """Base class for safe-to-handle identity-domain failures."""


class IdentityConflictError(IdentityServiceError):
    """The presented identity conflicts with an existing durable binding."""


class IdentityAccessDeniedError(IdentityServiceError):
    """The requested identity operation is not authorized locally."""


class InvalidLoginTransactionError(IdentityServiceError):
    """An OIDC state transaction is absent, expired, consumed, or invalid."""


@dataclass(frozen=True)
class VerifiedIdentity:
    """Identity claims after signature, issuer, audience, and time validation."""

    provider: str
    issuer: str
    subject: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    tenant_id: Optional[str] = None
    object_id: Optional[str] = None

    def __post_init__(self) -> None:
        for field_name in ("provider", "issuer", "subject"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")
        if bool(self.tenant_id) != bool(self.object_id):
            raise ValueError("tenant_id and object_id must be supplied together")


@dataclass(frozen=True)
class ProvisionedIdentity:
    organization: Organization
    app_user: AppUser
    identity: AuthIdentity
    membership: OrganizationMembership
    created_user: bool
    created_membership: bool

    @property
    def can_sign_in(self) -> bool:
        return (
            self.organization.status == AccessStatus.ACTIVE.value
            and self.app_user.status == AccessStatus.ACTIVE.value
            and self.membership.status == AccessStatus.ACTIVE.value
        )


@dataclass(frozen=True)
class SessionPrincipal:
    session_id: UUID
    app_user_id: UUID
    organization_id: UUID
    resource_owner_id: str
    role: str
    email: Optional[str]
    display_name: Optional[str]


def hash_opaque_token(token: str) -> str:
    """Return the storage-safe SHA-256 digest of an opaque high-entropy token."""

    if not token:
        raise ValueError("token is required")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class IdentityService:
    """Transactional repository for identity, membership, and session state.

    Methods flush but never commit. The request boundary owns commit/rollback so
    provisioning, blocking, session revocation, and audit events stay atomic.
    """

    def __init__(self, db: Session):
        self.db = db

    def provision_verified_identity(
        self,
        *,
        organization_slug: str,
        organization_name: str,
        verified_identity: VerifiedIdentity,
        role: OrganizationRole | str = OrganizationRole.USER,
        resource_owner_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> ProvisionedIdentity:
        """JIT-provision or refresh a verified external identity.

        A blocked user or membership is deliberately never reactivated by a
        successful identity-provider login. The caller must reject sign-in when
        the returned result's ``can_sign_in`` property is false.
        """

        slug = organization_slug.strip()
        name = organization_name.strip()
        if not slug or not name:
            raise ValueError("organization_slug and organization_name are required")
        role_value = OrganizationRole(role).value
        seen_at = now or utcnow()

        organization = self.db.scalar(
            select(Organization).where(Organization.slug == slug)
        )
        if organization is None:
            organization = Organization(
                slug=slug,
                name=name,
                status=AccessStatus.ACTIVE.value,
            )
            self.db.add(organization)
            self.db.flush()
        else:
            organization.name = name

        exact_identity = self.db.scalar(
            select(AuthIdentity).where(
                AuthIdentity.issuer == verified_identity.issuer,
                AuthIdentity.subject == verified_identity.subject,
            )
        )
        entra_identity = None
        if verified_identity.tenant_id and verified_identity.object_id:
            entra_identity = self.db.scalar(
                select(AuthIdentity).where(
                    AuthIdentity.provider == verified_identity.provider,
                    AuthIdentity.tenant_id == verified_identity.tenant_id,
                    AuthIdentity.object_id == verified_identity.object_id,
                )
            )
        if (
            exact_identity is not None
            and entra_identity is not None
            and exact_identity.id != entra_identity.id
        ):
            raise IdentityConflictError(
                "issuer/subject and tenant/object identify different users"
            )

        identity = exact_identity or entra_identity
        created_user = False
        if identity is None:
            app_user = None
            if resource_owner_id:
                app_user = self.db.scalar(
                    select(AppUser).where(
                        AppUser.resource_owner_id == resource_owner_id
                    )
                )
            if app_user is None:
                app_user_id = uuid4()
                app_user = AppUser(
                    id=app_user_id,
                    resource_owner_id=resource_owner_id or str(app_user_id),
                    email=verified_identity.email,
                    display_name=verified_identity.display_name,
                    status=AccessStatus.ACTIVE.value,
                )
                self.db.add(app_user)
                created_user = True
            identity = AuthIdentity(
                app_user=app_user,
                provider=verified_identity.provider,
                issuer=verified_identity.issuer,
                subject=verified_identity.subject,
                tenant_id=verified_identity.tenant_id,
                object_id=verified_identity.object_id,
                last_seen_at=seen_at,
            )
            self.db.add(identity)
            self.db.flush()
        else:
            app_user = identity.app_user
            if identity.provider != verified_identity.provider:
                raise IdentityConflictError(
                    "issuer/subject is already bound to another provider"
                )
            stored_entra_key = (identity.tenant_id, identity.object_id)
            presented_entra_key = (
                verified_identity.tenant_id,
                verified_identity.object_id,
            )
            if any(stored_entra_key) and stored_entra_key != presented_entra_key:
                raise IdentityConflictError(
                    "tenant/object does not match the existing identity binding"
                )
            if not any(stored_entra_key) and all(presented_entra_key):
                identity.tenant_id, identity.object_id = presented_entra_key
            identity.last_seen_at = seen_at

        if verified_identity.email:
            app_user.email = verified_identity.email
        if verified_identity.display_name:
            app_user.display_name = verified_identity.display_name

        membership = self.db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.app_user_id == app_user.id,
            )
        )
        created_membership = membership is None
        if membership is None:
            membership = OrganizationMembership(
                organization=organization,
                app_user=app_user,
                role=role_value,
                status=AccessStatus.ACTIVE.value,
            )
            self.db.add(membership)
        else:
            # Entra app-role changes take effect on the next verified login while
            # the independently managed local block remains authoritative.
            membership.role = role_value

        self.db.flush()
        result = ProvisionedIdentity(
            organization=organization,
            app_user=app_user,
            identity=identity,
            membership=membership,
            created_user=created_user,
            created_membership=created_membership,
        )
        if result.can_sign_in:
            app_user.last_login_at = seen_at
        self.db.flush()
        return result

    def create_session(
        self,
        *,
        app_user_id: UUID,
        organization_id: UUID,
        expires_at: datetime,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> tuple[str, AppSession]:
        """Create an opaque session after rechecking local access state."""

        created_at = now or utcnow()
        if _aware_utc(expires_at) <= _aware_utc(created_at):
            raise ValueError("expires_at must be in the future")
        app_user, organization, membership = self._load_access_state(
            app_user_id=app_user_id,
            organization_id=organization_id,
        )
        if not self._access_state_is_active(app_user, organization, membership):
            raise IdentityAccessDeniedError("user is blocked or inactive")

        raw_token = secrets.token_urlsafe(48)
        session = AppSession(
            app_user_id=app_user_id,
            organization_id=organization_id,
            token_hash=hash_opaque_token(raw_token),
            created_at=created_at,
            expires_at=expires_at,
            last_seen_at=created_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(session)
        self.db.flush()
        return raw_token, session

    def resolve_session(
        self,
        raw_token: str,
        *,
        now: Optional[datetime] = None,
    ) -> Optional[SessionPrincipal]:
        """Resolve a session and enforce current block state on every request."""

        checked_at = now or utcnow()
        session = self.db.scalar(
            select(AppSession).where(
                AppSession.token_hash == hash_opaque_token(raw_token)
            )
        )
        if session is None or session.revoked_at is not None:
            return None
        if _aware_utc(session.expires_at) <= _aware_utc(checked_at):
            session.revoked_at = checked_at
            session.revoked_reason = "expired"
            self.db.flush()
            return None

        app_user, organization, membership = self._load_access_state(
            app_user_id=session.app_user_id,
            organization_id=session.organization_id,
        )
        if not self._access_state_is_active(app_user, organization, membership):
            session.revoked_at = checked_at
            session.revoked_reason = "access_blocked"
            self.db.flush()
            return None

        session.last_seen_at = checked_at
        self.db.flush()
        return SessionPrincipal(
            session_id=session.id,
            app_user_id=app_user.id,
            organization_id=organization.id,
            resource_owner_id=app_user.resource_owner_id,
            role=membership.role,
            email=app_user.email,
            display_name=app_user.display_name,
        )

    def set_membership_status(
        self,
        *,
        organization_id: UUID,
        target_user_id: UUID,
        status: AccessStatus | str,
        actor_user_id: Optional[UUID] = None,
        reason: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> int:
        """Block/unblock a member and revoke all sessions when blocking.

        If an actor is supplied, this method independently verifies that they
        are an active organization admin before mutating access state.
        """

        status_value = AccessStatus(status).value
        changed_at = now or utcnow()
        if actor_user_id is not None:
            actor_user, organization, actor_membership = self._load_access_state(
                app_user_id=actor_user_id,
                organization_id=organization_id,
            )
            if (
                not self._access_state_is_active(
                    actor_user,
                    organization,
                    actor_membership,
                )
                or actor_membership.role != OrganizationRole.ADMIN.value
            ):
                raise IdentityAccessDeniedError("an active admin is required")

        membership = self.db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.app_user_id == target_user_id,
            )
        )
        if membership is None:
            raise IdentityAccessDeniedError("target user is not an organization member")

        membership.status = status_value
        revoked_count = 0
        if status_value == AccessStatus.BLOCKED.value:
            membership.blocked_at = changed_at
            membership.blocked_by_user_id = actor_user_id
            membership.block_reason = reason
            result = self.db.execute(
                update(AppSession)
                .where(
                    AppSession.organization_id == organization_id,
                    AppSession.app_user_id == target_user_id,
                    AppSession.revoked_at.is_(None),
                )
                .values(
                    revoked_at=changed_at,
                    revoked_reason="membership_blocked",
                )
            )
            revoked_count = int(result.rowcount or 0)
        else:
            membership.blocked_at = None
            membership.blocked_by_user_id = None
            membership.block_reason = None

        self.db.add(
            SecurityAuditEvent(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                target_user_id=target_user_id,
                event_type=f"membership.{status_value}",
                outcome="success",
                event_metadata={
                    "reason": reason,
                    "revoked_session_count": revoked_count,
                },
            )
        )
        self.db.flush()
        return revoked_count

    def revoke_session(
        self,
        raw_token: str,
        *,
        reason: str = "logout",
        now: Optional[datetime] = None,
    ) -> bool:
        session = self.db.scalar(
            select(AppSession).where(
                AppSession.token_hash == hash_opaque_token(raw_token)
            )
        )
        if session is None or session.revoked_at is not None:
            return False
        session.revoked_at = now or utcnow()
        session.revoked_reason = reason
        self.db.flush()
        return True

    def create_login_transaction(
        self,
        *,
        organization_id: UUID,
        state: str,
        browser_binding: str,
        nonce: str,
        code_verifier: str,
        redirect_uri: str,
        return_to: str,
        expires_at: datetime,
        provider: str = "oidc",
        now: Optional[datetime] = None,
    ) -> OIDCLoginTransaction:
        created_at = now or utcnow()
        if _aware_utc(expires_at) <= _aware_utc(created_at):
            raise ValueError("expires_at must be in the future")
        self._validate_return_to(return_to)
        if not all((state, browser_binding, nonce, code_verifier, redirect_uri, provider)):
            raise ValueError("OIDC transaction values are required")
        transaction = OIDCLoginTransaction(
            organization_id=organization_id,
            provider=provider,
            state_hash=hash_opaque_token(state),
            browser_binding_hash=hash_opaque_token(browser_binding),
            nonce=nonce,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
            return_to=return_to,
            created_at=created_at,
            expires_at=expires_at,
        )
        self.db.add(transaction)
        self.db.flush()
        return transaction

    def consume_login_transaction(
        self,
        state: str,
        browser_binding: str,
        *,
        now: Optional[datetime] = None,
    ) -> OIDCLoginTransaction:
        consumed_at = now or utcnow()
        if not state or not browser_binding:
            raise InvalidLoginTransactionError("invalid OIDC login transaction")
        transaction = self.db.scalar(
            select(OIDCLoginTransaction).where(
                OIDCLoginTransaction.state_hash == hash_opaque_token(state)
            )
        )
        if (
            transaction is None
            or transaction.consumed_at is not None
            or _aware_utc(transaction.expires_at) <= _aware_utc(consumed_at)
            or not hmac.compare_digest(
                transaction.browser_binding_hash,
                hash_opaque_token(browser_binding),
            )
        ):
            raise InvalidLoginTransactionError("invalid OIDC login transaction")

        updated = self.db.execute(
            update(OIDCLoginTransaction)
            .where(
                OIDCLoginTransaction.id == transaction.id,
                OIDCLoginTransaction.consumed_at.is_(None),
            )
            .values(consumed_at=consumed_at)
            .execution_options(synchronize_session="fetch")
        )
        if int(updated.rowcount or 0) != 1:
            raise InvalidLoginTransactionError("invalid OIDC login transaction")
        self.db.flush()
        return transaction

    @staticmethod
    def verify_nonce(transaction: OIDCLoginTransaction, presented_nonce: str) -> bool:
        return hmac.compare_digest(transaction.nonce, presented_nonce)

    @staticmethod
    def _validate_return_to(return_to: str) -> None:
        if (
            not return_to.startswith("/")
            or return_to.startswith("//")
            or "\\" in return_to
        ):
            raise ValueError("return_to must be a local absolute path")

    def _load_access_state(
        self,
        *,
        app_user_id: UUID,
        organization_id: UUID,
    ) -> tuple[AppUser, Organization, OrganizationMembership]:
        app_user = self.db.get(AppUser, app_user_id)
        organization = self.db.get(Organization, organization_id)
        membership = self.db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.app_user_id == app_user_id,
            )
        )
        if app_user is None or organization is None or membership is None:
            raise IdentityAccessDeniedError("organization access does not exist")
        return app_user, organization, membership

    @staticmethod
    def _access_state_is_active(
        app_user: AppUser,
        organization: Organization,
        membership: OrganizationMembership,
    ) -> bool:
        return (
            app_user.status == AccessStatus.ACTIVE.value
            and organization.status == AccessStatus.ACTIVE.value
            and membership.status == AccessStatus.ACTIVE.value
        )


def resource_owner_has_active_access(
    db: Session,
    resource_owner_id: str,
    *,
    require_managed_user: bool = False,
) -> bool:
    """Check background-work authorization before touching private resources.

    Legacy local/external-JWT users do not have ``AppUser`` rows, so callers can
    preserve those modes by leaving ``require_managed_user`` false. OIDC workers
    set it true: a missing mapping is denied rather than treated as legacy.
    """

    app_user = db.scalar(
        select(AppUser).where(AppUser.resource_owner_id == str(resource_owner_id))
    )
    if app_user is None:
        return not require_managed_user
    if app_user.status != AccessStatus.ACTIVE.value:
        return False
    active_membership_id = db.scalar(
        select(OrganizationMembership.id)
        .join(
            Organization,
            Organization.id == OrganizationMembership.organization_id,
        )
        .where(
            OrganizationMembership.app_user_id == app_user.id,
            OrganizationMembership.status == AccessStatus.ACTIVE.value,
            Organization.status == AccessStatus.ACTIVE.value,
        )
        .limit(1)
    )
    return active_membership_id is not None
