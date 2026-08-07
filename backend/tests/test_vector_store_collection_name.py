import re
import unittest

from app.services.vector_collection import collection_name_for_user


class VectorStoreCollectionNameTests(unittest.TestCase):
    def test_preserves_existing_valid_short_names(self):
        self.assertEqual(collection_name_for_user("local-admin"), "user_local-admin")

    def test_hashes_long_oidc_owner_id_within_chroma_limit(self):
        owner_id = "oidc-" + ("a" * 64)

        collection_name = collection_name_for_user(owner_id)

        self.assertLessEqual(len(collection_name), 63)
        self.assertRegex(collection_name, r"^[A-Za-z0-9][A-Za-z0-9_-]*[A-Za-z0-9]$")
        self.assertEqual(collection_name, collection_name_for_user(owner_id))
        self.assertNotIn(owner_id, collection_name)

    def test_hashes_unsafe_ids_without_colliding(self):
        first = collection_name_for_user("person@example.com/one")
        second = collection_name_for_user("person@example.com/two")

        self.assertNotEqual(first, second)
        self.assertIsNotNone(re.fullmatch(r"user_[a-f0-9]{56}", first))
        self.assertIsNotNone(re.fullmatch(r"user_[a-f0-9]{56}", second))


if __name__ == "__main__":
    unittest.main()
