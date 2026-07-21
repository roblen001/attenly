import unittest
from unittest.mock import patch

from app.routers import email_ingest


class EmailVerificationRedirectTests(unittest.IsolatedAsyncioTestCase):
    async def verify(self, result):
        with patch.object(email_ingest.config, "APP_URL", "http://localhost:5173/"):
            response = await email_ingest.verify_sender("test-token")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "http://localhost:5173/settings"
            f"?tab=email&sender_verification={result}",
        )

    async def test_success_returns_to_email_settings(self):
        with (
            patch.object(email_ingest, "is_email_ingest_enabled", return_value=True),
            patch.object(
                email_ingest.email_ingest_service,
                "verify_sender",
                return_value=(True, "verified"),
            ),
        ):
            await self.verify("success")

    async def test_invalid_or_expired_token_returns_clear_result(self):
        with (
            patch.object(email_ingest, "is_email_ingest_enabled", return_value=True),
            patch.object(
                email_ingest.email_ingest_service,
                "verify_sender",
                return_value=(False, "expired"),
            ),
        ):
            await self.verify("invalid")

    async def test_disabled_email_ingest_returns_clear_result(self):
        with patch.object(email_ingest, "is_email_ingest_enabled", return_value=False):
            await self.verify("disabled")

    async def test_unexpected_failure_returns_clear_result(self):
        with (
            patch.object(email_ingest, "is_email_ingest_enabled", return_value=True),
            patch.object(
                email_ingest.email_ingest_service,
                "verify_sender",
                side_effect=RuntimeError("provider failed"),
            ),
        ):
            await self.verify("failed")


if __name__ == "__main__":
    unittest.main()
