import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import FastAPI, HTTPException
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

from app import config
from app.db import get_db
from app.limits.slowapi import get_rate_limit, limiter, rate_limit_handler
from app.routers.auth import oidc_callback, oidc_login, oidc_logout, oidc_router
from app.services.oidc_auth import (
    CompletedOIDCLogin,
    OIDCSessionPrincipal,
    StartedOIDCLogin,
)


def _request(
    method: str,
    path: str,
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": headers or [],
            "client": ("192.0.2.10", 44321),
            "server": ("attenly.example", 443),
            "root_path": "",
            "app": MagicMock(),
        }
    )


class OIDCRouteCookieTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original = {
            name: getattr(config, name)
            for name in (
                "AUTH_PROVIDER",
                "OIDC_COOKIE_SECURE",
                "OIDC_LOGIN_COOKIE_NAME",
                "OIDC_SESSION_COOKIE_NAME",
                "OIDC_LOGIN_TTL_SECONDS",
                "OIDC_SESSION_TTL_HOURS",
                "APP_URL",
                "OIDC_CALLBACK_URL",
                "OIDC_ALLOWED_ORIGINS",
            )
        }
        config.AUTH_PROVIDER = "oidc"
        config.OIDC_COOKIE_SECURE = True
        config.OIDC_LOGIN_COOKIE_NAME = "__Host-attenly_oidc_flow"
        config.OIDC_SESSION_COOKIE_NAME = "__Host-attenly_session"
        config.OIDC_LOGIN_TTL_SECONDS = 600
        config.OIDC_SESSION_TTL_HOURS = 12
        config.APP_URL = "https://attenly.example"
        config.OIDC_CALLBACK_URL = "https://attenly.example/api/auth/oidc/callback"
        config.OIDC_ALLOWED_ORIGINS = ("https://attenly.example",)

    async def asyncTearDown(self):
        for name, value in self.original.items():
            setattr(config, name, value)

    async def test_login_sets_browser_binding_as_secure_host_only_cookie(self):
        with patch(
            "app.routers.auth.begin_oidc_login",
            new=AsyncMock(
                return_value=StartedOIDCLogin(
                    "https://idp.example/authorize",
                    "browser-binding",
                )
            ),
        ):
            response = await oidc_login(
                request=_request("GET", "/auth/oidc/login"),
                return_to="/agents",
                db=MagicMock(),
            )

        cookie = response.headers.getlist("set-cookie")[0]
        self.assertIn("__Host-attenly_oidc_flow=browser-binding", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("Path=/", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertNotIn("Domain=", cookie)

    async def test_successful_callback_sets_session_and_deletes_flow_cookie(self):
        principal = OIDCSessionPrincipal(
            resource_owner_id="oidc-owner",
            app_user_id="11111111-1111-1111-1111-111111111111",
            organization_id="22222222-2222-2222-2222-222222222222",
            organization_role="user",
            membership_status="active",
            email="user@example.com",
            display_name="User",
            created_at="2026-08-03T12:00:00+00:00",
        )
        request = _request(
            "GET",
            "/auth/oidc/callback",
            headers=[
                (
                    b"cookie",
                    b"__Host-attenly_oidc_flow=browser-binding",
                )
            ],
        )
        with patch(
            "app.routers.auth.complete_oidc_login",
            new=AsyncMock(
                return_value=CompletedOIDCLogin(
                    session_token="opaque-session",
                    return_to="/agents",
                    principal=principal,
                )
            ),
        ):
            response = await oidc_callback(
                request=request,
                code="code",
                state_value="state",
                provider_error=None,
                db=MagicMock(),
            )

        cookies = response.headers.getlist("set-cookie")
        self.assertEqual(response.headers["location"], "/agents")
        self.assertTrue(any("__Host-attenly_session=opaque-session" in value for value in cookies))
        self.assertTrue(any("__Host-attenly_oidc_flow=" in value and "Max-Age=0" in value for value in cookies))
        self.assertTrue(all("Domain=" not in value for value in cookies))

    async def test_failed_callback_deletes_flow_cookie_without_setting_session(self):
        database = MagicMock()
        with patch("app.routers.auth.audit_oidc_login_failure"):
            response = await oidc_callback(
                request=_request("GET", "/auth/oidc/callback"),
                code=None,
                state_value="state",
                provider_error="access_denied",
                db=database,
            )

        cookies = response.headers.getlist("set-cookie")
        self.assertEqual(response.headers["location"], "/login?auth_error=oidc_login_failed")
        self.assertTrue(any("__Host-attenly_oidc_flow=" in value and "Max-Age=0" in value for value in cookies))
        self.assertFalse(any("__Host-attenly_session=" in value for value in cookies))

    async def test_logout_requires_allowed_origin_and_deletes_session_cookie(self):
        with self.assertRaises(HTTPException) as missing_origin:
            await oidc_logout(
                request=_request("POST", "/auth/oidc/logout"),
                db=MagicMock(),
            )
        self.assertEqual(missing_origin.exception.status_code, 403)

        request = _request(
            "POST",
            "/auth/oidc/logout",
            headers=[
                (b"origin", b"https://attenly.example"),
                (b"cookie", b"__Host-attenly_session=opaque-session"),
            ],
        )
        with patch("app.routers.auth.revoke_oidc_session") as revoke:
            response = await oidc_logout(request=request, db=MagicMock())

        revoke.assert_called_once()
        cookie = response.headers.getlist("set-cookie")[0]
        self.assertIn("__Host-attenly_session=", cookie)
        self.assertIn("Max-Age=0", cookie)
        self.assertIn("Secure", cookie)
        self.assertNotIn("Domain=", cookie)

    async def test_oidc_route_limits_allow_corporate_burst_and_reject_spoofed_rotation(self):
        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
        app.include_router(oidc_router)
        app.dependency_overrides[get_db] = lambda: MagicMock()
        limiter._storage.reset()

        login_limit = int(get_rate_limit("oidc_login").split("/", 1)[0])
        callback_limit = int(get_rate_limit("oidc_callback").split("/", 1)[0])
        login_transport = httpx.ASGITransport(
            app=app,
            client=("198.51.100.10", 41000),
        )
        second_transport = httpx.ASGITransport(
            app=app,
            client=("198.51.100.11", 41001),
        )
        callback_transport = httpx.ASGITransport(
            app=app,
            client=("198.51.100.12", 41002),
        )

        try:
            with patch(
                "app.routers.auth.begin_oidc_login",
                new=AsyncMock(
                    return_value=StartedOIDCLogin(
                        "https://idp.example/authorize",
                        "browser-binding",
                    )
                ),
            ):
                async with httpx.AsyncClient(
                    transport=login_transport,
                    base_url="https://attenly.example",
                    follow_redirects=False,
                ) as client:
                    for _ in range(login_limit):
                        response = await client.get("/auth/oidc/login")
                        self.assertEqual(response.status_code, 303)
                    limited = await client.get("/auth/oidc/login")
                    spoofed = await client.get(
                        "/auth/oidc/login",
                        headers={"X-Forwarded-For": "203.0.113.99"},
                    )

                async with httpx.AsyncClient(
                    transport=second_transport,
                    base_url="https://attenly.example",
                    follow_redirects=False,
                ) as second_client:
                    independent = await second_client.get("/auth/oidc/login")

            self.assertEqual(limited.status_code, 429)
            self.assertIn("Retry-After", limited.headers)
            self.assertEqual(spoofed.status_code, 429)
            self.assertEqual(independent.status_code, 303)

            async with httpx.AsyncClient(
                transport=callback_transport,
                base_url="https://attenly.example",
                follow_redirects=False,
            ) as callback_client:
                for _ in range(callback_limit):
                    response = await callback_client.get(
                        "/auth/oidc/callback?error=access_denied"
                    )
                    self.assertEqual(response.status_code, 303)
                limited_callback = await callback_client.get(
                    "/auth/oidc/callback?error=access_denied"
                )

            self.assertEqual(limited_callback.status_code, 429)
            self.assertIn("Retry-After", limited_callback.headers)
        finally:
            limiter._storage.reset()


if __name__ == "__main__":
    unittest.main()
