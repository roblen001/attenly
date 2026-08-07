"""Stable, provider-agnostic ChromaDB collection naming."""

import hashlib
import re


_SAFE_COLLECTION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,61}[A-Za-z0-9]$")


def collection_name_for_user(user_id: str) -> str:
    """Return a stable Chroma-compatible collection name for a user.

    Preserve legacy names when they already meet Chroma's constraints. Long or
    unsafe identity-provider subjects are represented by a non-reversible hash.
    The hashed form is 61 characters, below Chroma's 63-character maximum.
    """
    legacy_name = f"user_{user_id}"
    if _SAFE_COLLECTION_NAME.fullmatch(legacy_name):
        return legacy_name

    user_digest = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:56]
    return f"user_{user_digest}"
