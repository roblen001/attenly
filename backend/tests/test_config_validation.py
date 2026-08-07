import unittest

from app import config


class ConfigurationPlaceholderTests(unittest.TestCase):
    def test_oidc_prepare_placeholders_are_rejected_at_runtime(self) -> None:
        for value in (
            "PASTE_ENTRA_TENANT_ID_HERE",
            "PASTE_ENTRA_APPLICATION_CLIENT_ID_HERE",
            "PASTE_ENTRA_CLIENT_SECRET_VALUE_HERE",
        ):
            with self.subTest(value=value):
                self.assertTrue(config._is_placeholder(value))


if __name__ == "__main__":
    unittest.main()
