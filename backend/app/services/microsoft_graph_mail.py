"""Small Microsoft Graph mail client used by inbound and outbound email.

The app uses Microsoft Graph with application permissions and the OAuth client
credentials flow. Keeping the HTTP client here avoids bringing in a Graph SDK
dependency and keeps token/request behavior shared across providers.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib import error, parse, request

logger = logging.getLogger(__name__)


class MicrosoftGraphMailClient:
    token_url_template = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    graph_base_url = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        tenant_id: Optional[str],
        client_id: Optional[str],
        client_secret: Optional[str],
        mailbox: Optional[str],
    ):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.mailbox = mailbox
        self._access_token: Optional[str] = None

    def is_configured(self) -> bool:
        return all([self.tenant_id, self.client_id, self.client_secret, self.mailbox])

    def _fetch_access_token(self) -> str:
        if not self.is_configured():
            raise RuntimeError("Microsoft Graph mail is not fully configured")

        body = parse.urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            }
        ).encode("utf-8")

        token_request = request.Request(
            self.token_url_template.format(tenant_id=self.tenant_id),
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        with request.urlopen(token_request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        token = payload.get("access_token")
        if not token:
            raise RuntimeError("Microsoft Graph token response did not include access_token")
        self._access_token = token
        return token

    def _token(self) -> str:
        return self._access_token or self._fetch_access_token()

    def _mailbox_path(self) -> str:
        if not self.mailbox:
            raise RuntimeError("GRAPH_MAILBOX is not configured")
        return f"/users/{parse.quote(self.mailbox, safe='')}"

    def request_json(
        self,
        method: str,
        path_or_url: str,
        *,
        query: Optional[Dict[str, str]] = None,
        payload: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        url = (
            path_or_url
            if path_or_url.startswith("https://")
            else f"{self.graph_base_url}{path_or_url}"
        )
        if query:
            url = f"{url}?{parse.urlencode(query)}"

        request_headers = {
            "Authorization": f"Bearer {self._token()}",
            "Accept": "application/json",
        }
        if headers:
            request_headers.update(headers)

        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

        graph_request = request.Request(
            url,
            data=data,
            headers=request_headers,
            method=method,
        )

        try:
            with request.urlopen(graph_request, timeout=30) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except error.HTTPError as exc:
            if exc.code == 401 and self._access_token:
                self._access_token = None
                return self.request_json(
                    method,
                    path_or_url,
                    query=query,
                    payload=payload,
                    headers=headers,
                )
            details = exc.read().decode("utf-8", errors="replace")
            logger.error("Microsoft Graph request failed: HTTP %s %s", exc.code, details)
            raise

    def send_mail(self, to: str, subject: str, body: str) -> None:
        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "Text",
                    "content": body,
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to,
                        }
                    }
                ],
            },
            "saveToSentItems": False,
        }
        self.request_json("POST", f"{self._mailbox_path()}/sendMail", payload=payload)

    def list_messages_since(self, since: datetime, *, top: int) -> List[Dict[str, Any]]:
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        since_text = since.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

        response = self.request_json(
            "GET",
            f"{self._mailbox_path()}/mailFolders/inbox/messages",
            query={
                "$select": ",".join(
                    [
                        "id",
                        "internetMessageId",
                        "subject",
                        "from",
                        "toRecipients",
                        "ccRecipients",
                        "receivedDateTime",
                        "bodyPreview",
                        "body",
                        "hasAttachments",
                    ]
                ),
                "$filter": f"receivedDateTime ge {since_text} and hasAttachments eq true",
                "$orderby": "receivedDateTime asc",
                "$top": str(top),
            },
            headers={"Prefer": 'outlook.body-content-type="text"'},
        )
        return response.get("value", [])

    def list_message_attachments(self, message_id: str) -> List[Dict[str, Any]]:
        response = self.request_json(
            "GET",
            f"{self._mailbox_path()}/messages/{parse.quote(message_id, safe='')}/attachments",
        )
        return response.get("value", [])
