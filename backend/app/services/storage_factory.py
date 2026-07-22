"""Configured binary storage factory."""

from app import config


def get_configured_storage_service():
    if config.STORAGE_PROVIDER == "filesystem":
        from app.services.filesystem_storage_service import get_filesystem_storage_service

        return get_filesystem_storage_service()

    from app.services.supabase_storage_service import SupabaseStorageService

    return SupabaseStorageService()
