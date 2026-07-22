"""Tests for accurately named file-upload safety checks."""

import unittest
from unittest import mock

from app.services.file_security import FileSecurityService


class FileSecurityServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        with mock.patch.object(FileSecurityService, "_init_magic", return_value=False):
            self.service = FileSecurityService(max_file_size_mb=1)

    def test_valid_upload_reports_basic_safety_checks(self) -> None:
        result = self.service.validate_upload(
            b"ordinary text",
            "notes.txt",
            "text/plain",
        )

        self.assertTrue(result["valid"])
        self.assertTrue(result["basic_safety_checks_passed"])
        self.assertNotIn("security_scan_passed", result)

    def test_binary_data_in_text_file_fails_basic_safety_checks(self) -> None:
        result = self.service.validate_upload(
            b"ordinary\x00text",
            "notes.txt",
            "text/plain",
        )

        self.assertFalse(result["valid"])
        self.assertFalse(result["basic_safety_checks_passed"])
        self.assertIn(
            "File failed basic safety validation: Text file contains binary data",
            result["errors"],
        )


if __name__ == "__main__":
    unittest.main()
