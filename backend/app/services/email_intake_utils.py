"""Shared helpers for inbound email intake providers."""

from __future__ import annotations

from typing import Iterable, Optional

from app.config import (
    EMAIL_ALLOWED_EXTENSIONS,
    EMAIL_MAX_ATTACHMENT_SIZE_MB,
)


def extract_instruction_text(email_body: str) -> str:
    """Extract user instructions before common forwarded-message markers."""
    forwarded_markers = [
        "---------- Forwarded message ---------",
        "Begin forwarded message:",
        "-------- Original Message --------",
        "From:",
    ]

    body_lower = email_body.lower()
    earliest_pos = len(email_body)

    for marker in forwarded_markers:
        pos = body_lower.find(marker.lower())
        if pos != -1 and pos < earliest_pos:
            earliest_pos = pos

    if earliest_pos < len(email_body):
        instruction_text = email_body[:earliest_pos].strip()
    else:
        instruction_text = email_body.strip()

    if not instruction_text or len(instruction_text) < 10:
        instruction_text = email_body.strip()

    return instruction_text


def validate_attachment(filename: str, size_bytes: int) -> tuple[bool, Optional[str]]:
    """Validate an inbound attachment against the same rules as file upload."""
    file_ext = "." + filename.split(".")[-1].lower() if "." in filename else ""
    if file_ext not in EMAIL_ALLOWED_EXTENSIONS:
        return False, f"Unsupported file type: {file_ext}"

    size_mb = size_bytes / (1024 * 1024)
    if size_mb > EMAIL_MAX_ATTACHMENT_SIZE_MB:
        return False, f"File too large: {size_mb:.1f}MB (max {EMAIL_MAX_ATTACHMENT_SIZE_MB}MB)"

    return True, None


def normalize_email_address(email: str | None) -> str:
    return (email or "").strip().lower()


def first_matching_endpoint_address(candidates: Iterable[str], lookup) -> tuple[str, dict | None]:
    """Return the first candidate address that resolves to an ingest endpoint."""
    for address in candidates:
        normalized = normalize_email_address(address)
        if not normalized:
            continue
        endpoint = lookup(normalized)
        if endpoint:
            return normalized, endpoint
    return "", None
