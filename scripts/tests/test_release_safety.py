"""Regression tests for safety-sensitive release helper behavior."""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import init_self_hosted_env  # noqa: E402
from smoke_self_hosted_compose import disposable_project_name  # noqa: E402
from trigger_microsoft_graph_poll import validated_api_url  # noqa: E402


class SecretPromptTests(unittest.TestCase):
    def test_secret_prompt_uses_getpass(self) -> None:
        fake_stdin = mock.Mock()
        fake_stdin.isatty.return_value = True

        with (
            mock.patch.object(init_self_hosted_env.sys, "stdin", fake_stdin),
            mock.patch.object(
                init_self_hosted_env.getpass,
                "getpass",
                return_value="hidden-value",
            ) as getpass_prompt,
            mock.patch("builtins.input") as plain_prompt,
        ):
            value = init_self_hosted_env.prompt_value(
                "GRAPH_CLIENT_SECRET",
                None,
                secret=True,
            )

        self.assertEqual(value, "hidden-value")
        getpass_prompt.assert_called_once()
        plain_prompt.assert_not_called()

    def test_non_secret_prompt_uses_input(self) -> None:
        fake_stdin = mock.Mock()
        fake_stdin.isatty.return_value = True

        with (
            mock.patch.object(init_self_hosted_env.sys, "stdin", fake_stdin),
            mock.patch("builtins.input", return_value="visible-value") as plain_prompt,
            mock.patch.object(init_self_hosted_env.getpass, "getpass") as getpass_prompt,
        ):
            value = init_self_hosted_env.prompt_value("GRAPH_MAILBOX", None)

        self.assertEqual(value, "visible-value")
        plain_prompt.assert_called_once()
        getpass_prompt.assert_not_called()

    @unittest.skipUnless(os.name == "posix", "POSIX permission semantics only")
    def test_new_env_file_is_owner_only_on_posix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            init_self_hosted_env.write_env(env_path, ["SECRET=value"], force=False)

            self.assertEqual(stat.S_IMODE(env_path.stat().st_mode), 0o600)
            self.assertEqual(env_path.read_text(encoding="utf-8"), "SECRET=value\n")

    @unittest.skipUnless(os.name == "posix", "POSIX permission semantics only")
    def test_existing_env_file_is_restricted_before_rewrite_on_posix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("OLD=value\n", encoding="utf-8")
            os.chmod(env_path, 0o644)

            init_self_hosted_env.write_env(env_path, ["SECRET=value"], force=True)

            self.assertEqual(stat.S_IMODE(env_path.stat().st_mode), 0o600)


class DisposableComposeProjectTests(unittest.TestCase):
    def test_reserved_smoke_project_names_are_accepted(self) -> None:
        self.assertEqual(disposable_project_name("attenly-smoke"), "attenly-smoke")
        self.assertEqual(
            disposable_project_name("attenly-smoke-ci_1"),
            "attenly-smoke-ci_1",
        )

    def test_non_smoke_project_names_are_rejected(self) -> None:
        for project_name in ("attenly", "production", "Attenly-smoke", "smoke-test"):
            with self.subTest(project_name=project_name):
                with self.assertRaises(argparse.ArgumentTypeError):
                    disposable_project_name(project_name)


class GraphPollUrlTests(unittest.TestCase):
    def test_https_and_loopback_http_urls_are_accepted(self) -> None:
        accepted = (
            "https://api.company.test/api",
            "http://localhost:5173/api",
            "http://service.localhost:8080/api",
            "http://127.0.0.1:8080/api",
            "http://[::1]:8080/api",
        )
        for api_url in accepted:
            with self.subTest(api_url=api_url):
                self.assertEqual(validated_api_url(api_url), api_url)

    def test_plaintext_non_loopback_urls_are_rejected(self) -> None:
        rejected = (
            "http://10.0.0.2:8080/api",
            "http://host.docker.internal:8080/api",
            "http://localhost.example.com/api",
        )
        for api_url in rejected:
            with self.subTest(api_url=api_url):
                with self.assertRaises(SystemExit):
                    validated_api_url(api_url)

    def test_ambiguous_or_credential_bearing_urls_are_rejected(self) -> None:
        rejected = (
            "localhost:5173/api",
            "ftp://localhost/api",
            "https://user:password@api.company.test/api",
            "https://api.company.test/api?secret=value",
            "https://api.company.test/api#fragment",
        )
        for api_url in rejected:
            with self.subTest(api_url=api_url):
                with self.assertRaises(SystemExit):
                    validated_api_url(api_url)


if __name__ == "__main__":
    unittest.main()
