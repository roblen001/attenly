import tempfile
import unittest
from pathlib import Path

from app.services.document_storage_service import DocumentStorageService


class DocumentStorageSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = DocumentStorageService(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_store_load_and_delete_round_trip(self):
        token = self.storage.store(
            {"text": "example"},
            user_id="local-admin",
            document_id="document-1",
            processor_type="pdf",
        )

        self.assertEqual({"text": "example"}, self.storage.load(token, "local-admin"))
        self.assertTrue(self.storage.delete(token, "local-admin"))

    def test_rejects_path_traversal_in_token(self):
        with self.assertRaisesRegex(ValueError, "Invalid document token"):
            self.storage.load("../another-user/document", "local-admin")

    def test_rejects_path_traversal_in_user_id(self):
        with self.assertRaisesRegex(ValueError, "Invalid user identifier"):
            self.storage.store({}, "../another-user", "document-1")

    def test_token_cannot_access_another_users_file(self):
        token = self.storage.store({}, "user-one", "document-1")

        with self.assertRaisesRegex(ValueError, "Document data not found"):
            self.storage.load(token, "user-two")

        self.assertTrue((Path(self.temp_dir.name) / "user-one" / f"{token}.json").exists())


if __name__ == "__main__":
    unittest.main()
