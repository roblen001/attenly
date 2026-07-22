"""Filesystem-backed document storage for local and enterprise pilots."""

import hashlib
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict

from app.config import FILESYSTEM_STORAGE_PATH

logger = logging.getLogger(__name__)


class FilesystemStorageService:
    """Store report document binaries on a mounted filesystem volume."""

    bucket_name = "filesystem"

    def __init__(self, root_path: str = FILESYSTEM_STORAGE_PATH):
        self.root_path = Path(root_path).expanduser().resolve()
        self.root_path.mkdir(parents=True, exist_ok=True)

    def _calculate_content_hash(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _construct_storage_path(self, user_id: str, report_id: str, content_hash: str) -> str:
        return f"{user_id}/{report_id}/{content_hash}.pdf"

    def _resolve_storage_path(self, storage_path: str) -> Path:
        resolved = (self.root_path / storage_path).resolve()
        if self.root_path not in resolved.parents and resolved != self.root_path:
            raise ValueError("Resolved storage path escapes filesystem storage root")
        return resolved

    def upload_document(
        self,
        access_token: str,
        refresh_token: str,
        user_id: str,
        document_id: str,
        pdf_bytes: bytes,
        report_id: str,
    ) -> Dict[str, str]:
        return self.upload_document_for_user(user_id, document_id, pdf_bytes, report_id)

    def upload_document_for_user(
        self,
        user_id: str,
        document_id: str,
        pdf_bytes: bytes,
        report_id: str,
        content_type: str = "application/pdf",
    ) -> Dict[str, str]:
        content_hash = self._calculate_content_hash(pdf_bytes)
        storage_path = self._construct_storage_path(user_id, report_id, content_hash)
        absolute_path = self._resolve_storage_path(storage_path)
        absolute_path.parent.mkdir(parents=True, exist_ok=True)

        duplicate = absolute_path.exists()
        if not duplicate:
            absolute_path.write_bytes(pdf_bytes)

        logger.info(
            "Stored document %s at %s (%s bytes, duplicate=%s)",
            document_id,
            storage_path,
            len(pdf_bytes),
            duplicate,
        )
        return {
            "storage_path": storage_path,
            "content_hash": content_hash,
            "bucket": self.bucket_name,
            "stored_at": datetime.now().isoformat(),
            "duplicate": duplicate,
        }

    def download_document(self, access_token: str, refresh_token: str, user_id: str, storage_path: str) -> bytes:
        return self.download_document_for_system(user_id, storage_path)

    def download_document_for_system(self, user_id: str, storage_path: str) -> bytes:
        if not storage_path.startswith(f"{user_id}/"):
            raise ValueError(f"Access denied: path {storage_path} does not belong to user {user_id}")

        absolute_path = self._resolve_storage_path(storage_path)
        return absolute_path.read_bytes()

    def delete_document(self, access_token: str, refresh_token: str, user_id: str, storage_path: str) -> bool:
        try:
            if not storage_path.startswith(f"{user_id}/"):
                raise ValueError(f"Access denied: path {storage_path} does not belong to user {user_id}")

            absolute_path = self._resolve_storage_path(storage_path)
            if absolute_path.exists():
                absolute_path.unlink()
            return True
        except Exception as exc:
            logger.error("Failed to delete filesystem document %s: %s", storage_path, exc)
            return False

    def cleanup_report_documents(self, access_token: str, refresh_token: str, user_id: str, report_id: str) -> int:
        report_dir = self._resolve_storage_path(f"{user_id}/{report_id}")
        if not report_dir.exists():
            return 0

        files = [path for path in report_dir.rglob("*") if path.is_file()]
        shutil.rmtree(report_dir)
        return len(files)

    def verify_content_hash(self, content: bytes, expected_hash: str) -> bool:
        return self._calculate_content_hash(content) == expected_hash


_filesystem_storage_service: FilesystemStorageService | None = None


def get_filesystem_storage_service() -> FilesystemStorageService:
    global _filesystem_storage_service
    if _filesystem_storage_service is None:
        _filesystem_storage_service = FilesystemStorageService()
    return _filesystem_storage_service
