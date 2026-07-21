import unittest
from datetime import datetime, timezone

from app.services.microsoft_graph_mail import MicrosoftGraphMailClient


class MicrosoftGraphMailClientTests(unittest.TestCase):
    def test_inbound_poll_reads_only_the_inbox(self):
        client = MicrosoftGraphMailClient(
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
            mailbox="attenly@example.com",
        )
        captured = {}

        def fake_request(method, path, *, query=None, payload=None, headers=None):
            captured.update(
                {
                    "method": method,
                    "path": path,
                    "query": query,
                }
            )
            return {"value": [{"id": "message-1"}]}

        client.request_json = fake_request
        messages = client.list_messages_since(
            datetime(2026, 7, 21, tzinfo=timezone.utc),
            top=25,
        )

        self.assertEqual(messages, [{"id": "message-1"}])
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(
            captured["path"],
            "/users/attenly%40example.com/mailFolders/inbox/messages",
        )
        self.assertIn("hasAttachments eq true", captured["query"]["$filter"])


if __name__ == "__main__":
    unittest.main()
