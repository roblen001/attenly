"""Shared Supabase client construction.

Supabase remains the default provider, but open-source profiles can now boot
without importing the Supabase SDK unless Supabase credentials are configured.
"""

import logging
from typing import Any

from app.config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)


def create_supabase_client() -> Any | None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    try:
        from supabase import create_client
    except ImportError as exc:
        logger.warning("Supabase SDK is not installed: %s", exc)
        return None

    return create_client(SUPABASE_URL, SUPABASE_KEY)


supabase_client = create_supabase_client()
