import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    AppSession,
    AppUser,
    OIDCLoginTransaction,
    SecurityAuditEvent,
)
from app.services.identity_service import (
    AccessStatus,
    IdentityConflictError,
    IdentityAccessDeniedError,
    IdentityService,
    InvalidLoginTransactionError,
    OrganizationRole,
    VerifiedIdentity,
    resource_owner_has_active_access,
)


class IdentityServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)
        self.db = self.Session()
        self.service = IdentityService(self.db)
        self.now = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @staticmethod
    def entra_identity(
        *,
        issuer="https://login.microsoftonline.com/tenant-1/v2.0",
        subject="subject-1",
        object_id="object-1",
        email="person@example.com",
        display_name="Person One",
    ):
        return VerifiedIdentity(
            provider="oidc",
            issuer=issuer,
            subject=subject,
            tenant_id="tenant-1",
            object_id=object_id,
            email=email,
            display_name=display_name,
        )

    def provision(self, *, role=OrganizationRole.USER, identity=None):
        return self.service.provision_verified_identity(
            organization_slug="example",
            organization_name="Example Corp",
            verified_identity=identity or self.entra_identity(),
            role=role,
            now=self.now,
        )

    def test_jit_provisioning_is_stable_and_syncs_role(self):
        initial = self.provision()

        self.assertTrue(initial.created_user)
        self.assertTrue(initial.created_membership)
        self.assertTrue(initial.can_sign_in)
        self.assertEqual(initial.membership.role, "user")
        self.assertEqual(
            initial.app_user.resource_owner_id,
            str(initial.app_user.id),
        )

        refreshed = self.service.provision_verified_identity(
            organization_slug="example",
            organization_name="Example Corporation",
            verified_identity=self.entra_identity(
                email="renamed@example.com",
                display_name="Renamed Person",
            ),
            role=OrganizationRole.ADMIN,
            now=self.now + timedelta(minutes=1),
        )

        self.assertFalse(refreshed.created_user)
        self.assertFalse(refreshed.created_membership)
        self.assertEqual(refreshed.app_user.id, initial.app_user.id)
        self.assertEqual(refreshed.app_user.resource_owner_id, initial.app_user.resource_owner_id)
        self.assertEqual(refreshed.app_user.email, "renamed@example.com")
        self.assertEqual(refreshed.membership.role, "admin")
        self.assertEqual(refreshed.organization.name, "Example Corporation")

        # Entra's tenant/object pair remains the canonical account key if an
        # app migration changes its issuer/subject pair.
        migrated_client = self.service.provision_verified_identity(
            organization_slug="example",
            organization_name="Example Corporation",
            verified_identity=self.entra_identity(
                issuer="https://login.microsoftonline.com/tenant-1/migrated/v2.0",
                subject="new-pairwise-subject",
            ),
            role=OrganizationRole.ADMIN,
            now=self.now + timedelta(minutes=2),
        )
        self.assertEqual(migrated_client.app_user.id, initial.app_user.id)
        self.assertEqual(
            migrated_client.app_user.resource_owner_id,
            initial.app_user.resource_owner_id,
        )

    def test_existing_resource_owner_can_be_explicitly_linked(self):
        legacy_user = AppUser(
            resource_owner_id="legacy-private-owner",
            email="legacy@example.com",
            status="active",
        )
        self.db.add(legacy_user)
        self.db.flush()

        result = self.service.provision_verified_identity(
            organization_slug="example",
            organization_name="Example Corp",
            verified_identity=self.entra_identity(),
            resource_owner_id="legacy-private-owner",
            now=self.now,
        )

        self.assertFalse(result.created_user)
        self.assertEqual(result.app_user.id, legacy_user.id)
        self.assertEqual(result.app_user.resource_owner_id, "legacy-private-owner")

    def test_conflicting_provider_cannot_claim_existing_issuer_subject(self):
        self.provision()
        conflicting = VerifiedIdentity(
            provider="different-provider",
            issuer="https://login.microsoftonline.com/tenant-1/v2.0",
            subject="subject-1",
        )

        with self.assertRaises(IdentityConflictError):
            self.service.provision_verified_identity(
                organization_slug="example",
                organization_name="Example Corp",
                verified_identity=conflicting,
                now=self.now,
            )

    def test_session_stores_only_hash_and_block_revokes_immediately(self):
        admin = self.provision(role=OrganizationRole.ADMIN)
        member = self.provision(
            identity=self.entra_identity(
                subject="subject-2",
                object_id="object-2",
                email="member@example.com",
            )
        )
        raw_token, session = self.service.create_session(
            app_user_id=member.app_user.id,
            organization_id=member.organization.id,
            expires_at=self.now + timedelta(hours=8),
            ip_address="192.0.2.10",
            user_agent="test-agent",
            now=self.now,
        )

        self.assertNotEqual(session.token_hash, raw_token)
        self.assertNotIn(raw_token, session.token_hash)
        principal = self.service.resolve_session(
            raw_token,
            now=self.now + timedelta(minutes=1),
        )
        self.assertIsNotNone(principal)
        self.assertEqual(principal.resource_owner_id, member.app_user.resource_owner_id)
        self.assertEqual(principal.role, "user")

        revoked_count = self.service.set_membership_status(
            organization_id=member.organization.id,
            target_user_id=member.app_user.id,
            status=AccessStatus.BLOCKED,
            actor_user_id=admin.app_user.id,
            reason="departed",
            now=self.now + timedelta(minutes=2),
        )

        self.assertEqual(revoked_count, 1)
        self.assertIsNone(
            self.service.resolve_session(
                raw_token,
                now=self.now + timedelta(minutes=3),
            )
        )
        persisted_session = self.db.scalar(
            select(AppSession).where(AppSession.id == session.id)
        )
        self.assertEqual(persisted_session.revoked_reason, "membership_blocked")
        audit = self.db.scalar(
            select(SecurityAuditEvent).where(
                SecurityAuditEvent.target_user_id == member.app_user.id
            )
        )
        self.assertEqual(audit.event_type, "membership.blocked")
        self.assertEqual(audit.event_metadata["revoked_session_count"], 1)

        reprovisioned = self.service.provision_verified_identity(
            organization_slug="example",
            organization_name="Example Corp",
            verified_identity=self.entra_identity(
                subject="subject-2",
                object_id="object-2",
                email="member@example.com",
            ),
            now=self.now + timedelta(minutes=4),
        )
        self.assertFalse(reprovisioned.can_sign_in)
        self.assertEqual(reprovisioned.membership.status, "blocked")

    def test_background_access_requires_active_managed_user_and_membership(self):
        member = self.provision()
        self.assertTrue(
            resource_owner_has_active_access(
                self.db,
                member.app_user.resource_owner_id,
                require_managed_user=True,
            )
        )
        member.membership.status = "blocked"
        self.db.flush()
        self.assertFalse(
            resource_owner_has_active_access(
                self.db,
                member.app_user.resource_owner_id,
                require_managed_user=True,
            )
        )
        self.assertFalse(
            resource_owner_has_active_access(
                self.db,
                "missing-oidc-owner",
                require_managed_user=True,
            )
        )
        self.assertTrue(
            resource_owner_has_active_access(
                self.db,
                "legacy-local-owner",
                require_managed_user=False,
            )
        )

    def test_blocked_admin_or_organization_cannot_change_membership(self):
        admin = self.provision(role=OrganizationRole.ADMIN)
        member = self.provision(
            identity=self.entra_identity(
                subject="subject-2",
                object_id="object-2",
                email="member@example.com",
            )
        )

        admin.app_user.status = "blocked"
        self.db.flush()
        with self.assertRaises(IdentityAccessDeniedError):
            self.service.set_membership_status(
                organization_id=admin.organization.id,
                target_user_id=member.app_user.id,
                status=AccessStatus.BLOCKED,
                actor_user_id=admin.app_user.id,
                now=self.now + timedelta(minutes=1),
            )

        admin.app_user.status = "active"
        admin.organization.status = "blocked"
        self.db.flush()
        with self.assertRaises(IdentityAccessDeniedError):
            self.service.set_membership_status(
                organization_id=admin.organization.id,
                target_user_id=member.app_user.id,
                status=AccessStatus.BLOCKED,
                actor_user_id=admin.app_user.id,
                now=self.now + timedelta(minutes=2),
            )

    def test_login_transaction_is_one_time_and_rejects_external_return(self):
        provisioned = self.provision()
        transaction = self.service.create_login_transaction(
            organization_id=provisioned.organization.id,
            state="raw-secret-state",
            browser_binding="raw-browser-binding",
            nonce="raw-secret-nonce",
            code_verifier="pkce-verifier",
            redirect_uri="https://attenly.example/api/auth/oidc/callback",
            return_to="/agents",
            expires_at=self.now + timedelta(minutes=5),
            now=self.now,
        )

        self.assertNotEqual(transaction.state_hash, "raw-secret-state")
        self.assertNotEqual(transaction.browser_binding_hash, "raw-browser-binding")
        consumed = self.service.consume_login_transaction(
            "raw-secret-state",
            "raw-browser-binding",
            now=self.now + timedelta(minutes=1),
        )
        self.assertEqual(consumed.id, transaction.id)
        self.assertTrue(self.service.verify_nonce(consumed, "raw-secret-nonce"))
        self.assertFalse(self.service.verify_nonce(consumed, "wrong-nonce"))
        with self.assertRaises(InvalidLoginTransactionError):
            self.service.consume_login_transaction(
                "raw-secret-state",
                "raw-browser-binding",
                now=self.now + timedelta(minutes=2),
            )

        stored_count = len(self.db.scalars(select(OIDCLoginTransaction)).all())
        self.assertEqual(stored_count, 1)
        with self.assertRaises(ValueError):
            self.service.create_login_transaction(
                organization_id=provisioned.organization.id,
                state="state-2",
                browser_binding="browser-binding-2",
                nonce="nonce-2",
                code_verifier="pkce-verifier-2",
                redirect_uri="https://attenly.example/api/auth/oidc/callback",
                return_to="https://evil.example/",
                expires_at=self.now + timedelta(minutes=5),
                now=self.now,
            )


if __name__ == "__main__":
    unittest.main()
