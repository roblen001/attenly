import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import config
from app.db import Base
from app.models import AppSession, OIDCLoginTransaction, SecurityAuditEvent
from app.services.oidc_auth import (
    OIDCAuthenticationError,
    OIDCAuthorizationError,
    _validate_id_token,
    audit_oidc_login_failure,
    authenticate_oidc_session,
    begin_oidc_login,
    complete_oidc_login,
    list_organization_users,
    sanitize_return_to,
    set_organization_user_status,
)


class OIDCAuthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)
        self.db = self.Session()
        self.original_config = {}
        overrides = {
            "OIDC_DISCOVERY_URL": "https://login.example/.well-known/openid-configuration",
            "OIDC_CLIENT_ID": "attenly-client",
            "OIDC_CLIENT_SECRET": "test-secret",
            "OIDC_CLIENT_AUTH_METHOD": "client_secret_post",
            "OIDC_SCOPES": "openid profile email",
            "OIDC_CALLBACK_URL": "https://attenly.example/api/auth/oidc/callback",
            "OIDC_EXPECTED_ISSUER": "https://login.example/tenant/v2.0",
            "OIDC_ALLOWED_ID_TOKEN_ALGORITHMS": ("RS256",),
            "OIDC_ROLES_CLAIM": "roles",
            "OIDC_USER_ROLE": "Attenly.User",
            "OIDC_ADMIN_ROLE": "Attenly.Admin",
            "OIDC_TENANT_ID": "tenant-id",
            "OIDC_ORGANIZATION_SLUG": "example",
            "OIDC_ORGANIZATION_NAME": "Example Corp",
            "OIDC_SESSION_TTL_HOURS": 12,
            "OIDC_LOGIN_TTL_SECONDS": 600,
        }
        for name, value in overrides.items():
            self.original_config[name] = getattr(config, name)
            setattr(config, name, value)
        self.metadata = {
            "issuer": "https://login.example/tenant/v2.0",
            "authorization_endpoint": "https://login.example/authorize",
            "token_endpoint": "https://login.example/token",
            "jwks_uri": "https://login.example/jwks",
        }

    async def asyncTearDown(self):
        for name, value in self.original_config.items():
            setattr(config, name, value)
        self.db.close()
        self.engine.dispose()

    async def begin(self, return_to="/dashboard"):
        with patch(
            "app.services.oidc_auth.get_provider_metadata",
            new=AsyncMock(return_value=self.metadata),
        ):
            started = await begin_oidc_login(self.db, return_to)
        query = parse_qs(urlsplit(started.authorization_url).query)
        return started.authorization_url, query["state"][0], started.browser_binding

    async def complete(self, state, browser_binding, claims):
        with (
            patch(
                "app.services.oidc_auth.get_provider_metadata",
                new=AsyncMock(return_value=self.metadata),
            ),
            patch(
                "app.services.oidc_auth._exchange_code",
                new=AsyncMock(return_value={"id_token": "provider-token"}),
            ),
            patch(
                "app.services.oidc_auth._validate_id_token",
                new=AsyncMock(return_value=claims),
            ),
        ):
            return await complete_oidc_login(
                self.db,
                state=state,
                code="authorization-code",
                browser_binding=browser_binding,
            )

    async def test_begin_login_uses_pkce_and_server_side_hashed_state(self):
        authorization_url, state, browser_binding = await self.begin("https://evil.example/")
        query = parse_qs(urlsplit(authorization_url).query)

        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["redirect_uri"], [config.OIDC_CALLBACK_URL])
        self.assertNotIn("client_secret", query)
        transaction = self.db.scalar(select(OIDCLoginTransaction))
        self.assertNotEqual(transaction.state_hash, state)
        self.assertNotEqual(transaction.browser_binding_hash, browser_binding)
        self.assertEqual(transaction.return_to, "/")

    async def test_callback_state_is_bound_to_the_browser_and_remains_one_time(self):
        _, state, browser_binding = await self.begin()
        claims = {
            "iss": self.metadata["issuer"],
            "sub": "browser-bound-subject",
            "tid": "tenant-id",
            "oid": "browser-bound-object",
            "email": "bound@example.com",
            "roles": ["Attenly.User"],
        }

        with self.assertRaises(OIDCAuthenticationError):
            await self.complete(state, "binding-from-a-different-browser", claims)

        transaction = self.db.scalar(select(OIDCLoginTransaction))
        self.assertIsNone(transaction.consumed_at)
        completed = await self.complete(state, browser_binding, claims)
        self.assertEqual(completed.principal.email, "bound@example.com")
        with self.assertRaises(OIDCAuthenticationError):
            await self.complete(state, browser_binding, claims)

    async def test_public_callback_failure_audit_is_browser_bound_and_one_time(self):
        _, state, browser_binding = await self.begin()

        self.assertFalse(
            audit_oidc_login_failure(
                self.db,
                state="fabricated-state",
                browser_binding="fabricated-binding",
                reason="provider_error",
            )
        )
        self.assertFalse(
            audit_oidc_login_failure(
                self.db,
                state=state,
                browser_binding="wrong-browser",
                reason="provider_error",
            )
        )
        self.assertEqual(self.db.scalars(select(SecurityAuditEvent)).all(), [])

        self.assertTrue(
            audit_oidc_login_failure(
                self.db,
                state=state,
                browser_binding=browser_binding,
                reason="provider_error",
            )
        )
        self.assertFalse(
            audit_oidc_login_failure(
                self.db,
                state=state,
                browser_binding=browser_binding,
                reason="provider_error",
            )
        )
        audits = self.db.scalars(select(SecurityAuditEvent)).all()
        self.assertEqual(len(audits), 1)
        transaction = self.db.scalar(select(OIDCLoginTransaction))
        self.assertIsNotNone(transaction.consumed_at)

    async def test_jit_sessions_admin_listing_and_immediate_block(self):
        _, admin_state, admin_binding = await self.begin()
        admin = await self.complete(
            admin_state,
            admin_binding,
            {
                "iss": self.metadata["issuer"],
                "sub": "admin-subject",
                "tid": "tenant-id",
                "oid": "admin-object",
                "email": "admin@example.com",
                "name": "Admin User",
                "roles": ["Attenly.Admin"],
            },
        )
        _, member_state, member_binding = await self.begin("/agents")
        member = await self.complete(
            member_state,
            member_binding,
            {
                "iss": self.metadata["issuer"],
                "sub": "member-subject",
                "tid": "tenant-id",
                "oid": "member-object",
                "preferred_username": "member@example.com",
                "name": "Member User",
                "roles": ["Attenly.User"],
            },
        )

        self.assertEqual(member.return_to, "/agents")
        self.assertEqual(member.principal.organization_role, "user")
        self.assertEqual(
            authenticate_oidc_session(self.db, member.session_token).app_user_id,
            member.principal.app_user_id,
        )
        stored_sessions = self.db.scalars(select(AppSession)).all()
        self.assertEqual(len(stored_sessions), 2)
        self.assertTrue(all(row.token_hash not in {admin.session_token, member.session_token} for row in stored_sessions))

        users = list_organization_users(self.db, admin.principal)
        self.assertEqual({row["email"] for row in users}, {"admin@example.com", "member@example.com"})
        updated = set_organization_user_status(
            self.db,
            admin.principal,
            member.principal.app_user_id,
            "blocked",
            reason="left company",
        )
        self.assertEqual(updated["status"], "blocked")
        with self.assertRaises(OIDCAuthenticationError):
            authenticate_oidc_session(self.db, member.session_token)

    async def test_generic_provider_ignores_entra_claim_names_across_issuers(self):
        config.OIDC_TENANT_ID = None
        _, state, binding = await self.begin()
        first_login = await self.complete(
            state,
            binding,
            {
                "iss": self.metadata["issuer"],
                "sub": "generic-subject",
                "tid": "unrelated-provider-value",
                "oid": "coincidental-object",
                "email": "generic@example.com",
                "roles": ["Attenly.User"],
            },
        )
        _, second_state, second_binding = await self.begin()
        second_login = await self.complete(
            second_state,
            second_binding,
            {
                "iss": "https://different-issuer.example",
                "sub": "different-subject",
                "tid": "unrelated-provider-value",
                "oid": "coincidental-object",
                "email": "other@example.com",
                "roles": ["Attenly.User"],
            },
        )
        self.assertEqual(first_login.principal.email, "generic@example.com")
        self.assertNotEqual(
            first_login.principal.app_user_id,
            second_login.principal.app_user_id,
        )

    async def test_missing_app_role_is_denied_and_audited(self):
        _, state, binding = await self.begin()
        with self.assertRaises(OIDCAuthorizationError):
            await self.complete(
                state,
                binding,
                {
                    "iss": self.metadata["issuer"],
                    "sub": "unassigned-subject",
                    "tid": "tenant-id",
                    "oid": "unassigned-object",
                    "roles": [],
                },
            )
        audit = self.db.scalar(
            select(SecurityAuditEvent).where(
                SecurityAuditEvent.event_type == "oidc.login",
                SecurityAuditEvent.outcome == "failure",
            )
        )
        self.assertIsNotNone(audit)
        self.assertEqual(audit.event_metadata["reason"], "OIDCAuthorizationError")

    async def test_wrong_entra_tenant_is_denied(self):
        _, state, binding = await self.begin()
        with self.assertRaises(OIDCAuthorizationError):
            await self.complete(
                state,
                binding,
                {
                    "iss": self.metadata["issuer"],
                    "sub": "other-tenant-subject",
                    "tid": "different-tenant",
                    "oid": "other-tenant-object",
                    "roles": ["Attenly.User"],
                },
            )

    async def test_rs256_id_token_signature_audience_issuer_and_nonce(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(
            private_key.public_key(),
            as_dict=True,
        )
        public_jwk.update({"kid": "signing-key", "use": "sig", "alg": "RS256"})
        now = datetime.now(timezone.utc)
        raw_token = jwt.encode(
            {
                "iss": self.metadata["issuer"],
                "sub": "signed-subject",
                "aud": config.OIDC_CLIENT_ID,
                "iat": now,
                "exp": now + timedelta(minutes=5),
                "nonce": "expected-nonce",
                "roles": ["Attenly.User"],
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "signing-key"},
        )
        with patch(
            "app.services.oidc_auth._get_jwks",
            new=AsyncMock(return_value={"keys": [public_jwk]}),
        ):
            claims = await _validate_id_token(
                self.metadata,
                raw_token,
                "expected-nonce",
            )
            self.assertEqual(claims["sub"], "signed-subject")
            with self.assertRaises(OIDCAuthenticationError):
                await _validate_id_token(self.metadata, raw_token, "wrong-nonce")

            wrong_azp_token = jwt.encode(
                {
                    "iss": self.metadata["issuer"],
                    "sub": "signed-subject",
                    "aud": config.OIDC_CLIENT_ID,
                    "azp": "different-client",
                    "iat": now,
                    "exp": now + timedelta(minutes=5),
                    "nonce": "expected-nonce",
                },
                private_key,
                algorithm="RS256",
                headers={"kid": "signing-key"},
            )
            with self.assertRaises(OIDCAuthenticationError):
                await _validate_id_token(
                    self.metadata,
                    wrong_azp_token,
                    "expected-nonce",
                )

            wrong_audience_token = jwt.encode(
                {
                    "iss": self.metadata["issuer"],
                    "sub": "signed-subject",
                    "aud": "different-client",
                    "iat": now,
                    "exp": now + timedelta(minutes=5),
                    "nonce": "expected-nonce",
                },
                private_key,
                algorithm="RS256",
                headers={"kid": "signing-key"},
            )
            with self.assertRaises(OIDCAuthenticationError):
                await _validate_id_token(
                    self.metadata,
                    wrong_audience_token,
                    "expected-nonce",
                )

            expired_token = jwt.encode(
                {
                    "iss": self.metadata["issuer"],
                    "sub": "signed-subject",
                    "aud": config.OIDC_CLIENT_ID,
                    "iat": now - timedelta(minutes=20),
                    "exp": now - timedelta(minutes=10),
                    "nonce": "expected-nonce",
                },
                private_key,
                algorithm="RS256",
                headers={"kid": "signing-key"},
            )
            with self.assertRaises(OIDCAuthenticationError):
                await _validate_id_token(
                    self.metadata,
                    expired_token,
                    "expected-nonce",
                )

        mismatched_jwk = dict(public_jwk)
        mismatched_jwk["alg"] = "RS384"
        with patch(
            "app.services.oidc_auth._get_jwks",
            new=AsyncMock(return_value={"keys": [mismatched_jwk]}),
        ):
            with self.assertRaises(OIDCAuthenticationError):
                await _validate_id_token(
                    self.metadata,
                    raw_token,
                    "expected-nonce",
                )

    def test_return_to_rejects_open_redirect_shapes(self):
        self.assertEqual(sanitize_return_to("//evil.example/path"), "/")
        self.assertEqual(sanitize_return_to("/\\evil.example"), "/")
        self.assertEqual(sanitize_return_to("https://evil.example"), "/")
        self.assertEqual(sanitize_return_to("/agents?tab=mine"), "/agents?tab=mine")


if __name__ == "__main__":
    unittest.main()
