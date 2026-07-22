import unittest
from unittest.mock import patch

from app.routers import email_ingest


class EmailDeliveryAddressTests(unittest.TestCase):
    settings = {
        "endpoint": {
            "id": "endpoint-1",
            "full_address": "u_abc123@example.onmicrosoft.com",
            "is_active": True,
            "default_agent_id": None,
        },
        "verified_senders": [],
        "usage_summary": {"jobs_last_24h": 0, "rate_limit": 0},
    }

    def test_local_graph_uses_configured_mailbox(self):
        with (
            patch.object(email_ingest.config, "INBOUND_EMAIL_PROVIDER", "microsoft_graph"),
            patch.object(email_ingest.config, "AUTH_PROVIDER", "local"),
            patch.object(
                email_ingest.config,
                "GRAPH_MAILBOX",
                "Attenly@Example.OnMicrosoft.com",
            ),
        ):
            result = email_ingest.with_delivery_config(self.settings)

        self.assertEqual(result["delivery_address"], "attenly@example.onmicrosoft.com")
        self.assertEqual(result["delivery_mode"], "graph_mailbox")
        self.assertEqual(
            result["endpoint"]["full_address"],
            "u_abc123@example.onmicrosoft.com",
        )

    def test_external_graph_keeps_generated_alias(self):
        with (
            patch.object(email_ingest.config, "INBOUND_EMAIL_PROVIDER", "microsoft_graph"),
            patch.object(email_ingest.config, "AUTH_PROVIDER", "external_jwt"),
            patch.object(email_ingest.config, "GRAPH_MAILBOX", "attenly@example.com"),
        ):
            result = email_ingest.with_delivery_config(self.settings)

        self.assertEqual(
            result["delivery_address"],
            "u_abc123@example.onmicrosoft.com",
        )
        self.assertEqual(result["delivery_mode"], "generated_alias")

    def test_non_graph_provider_keeps_generated_alias(self):
        with (
            patch.object(email_ingest.config, "INBOUND_EMAIL_PROVIDER", "resend"),
            patch.object(email_ingest.config, "AUTH_PROVIDER", "local"),
            patch.object(email_ingest.config, "GRAPH_MAILBOX", "attenly@example.com"),
        ):
            result = email_ingest.with_delivery_config(self.settings)

        self.assertEqual(
            result["delivery_address"],
            "u_abc123@example.onmicrosoft.com",
        )
        self.assertEqual(result["delivery_mode"], "generated_alias")

    def test_missing_endpoint_has_no_generated_delivery_address(self):
        settings = {**self.settings, "endpoint": None}
        with (
            patch.object(email_ingest.config, "INBOUND_EMAIL_PROVIDER", "resend"),
            patch.object(email_ingest.config, "AUTH_PROVIDER", "local"),
            patch.object(email_ingest.config, "GRAPH_MAILBOX", None),
        ):
            result = email_ingest.with_delivery_config(settings)

        self.assertIsNone(result["delivery_address"])
        self.assertIsNone(result["delivery_mode"])


if __name__ == "__main__":
    unittest.main()
