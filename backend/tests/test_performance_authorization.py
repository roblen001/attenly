import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException

from app.routers import performance as performance_router
from app.services.performance_monitor import FileProcessingPerformanceMonitor


class _StubPerformanceMonitor:
    def get_performance_summary(self, last_n_files: int):
        return {
            "summary": {"total_files_processed": 2},
            "recent_errors": ["private-filename.pdf failed"],
            "limit": last_n_files,
        }

    def build_export_data(self, last_n_files: int):
        return {"total_sessions": 2, "limit": last_n_files}


class PerformanceAuthorizationTests(unittest.TestCase):
    @staticmethod
    def _user(provider: str, role=None):
        return SimpleNamespace(
            id=f"{provider}-owner",
            provider=provider,
            organization_role=role,
        )

    def test_oidc_member_cannot_read_or_export_process_global_metrics(self):
        member = self._user("oidc", "user")

        with self.assertRaises(HTTPException) as report_error:
            asyncio.run(performance_router.get_performance_report(current_user=member))
        with self.assertRaises(HTTPException) as export_error:
            asyncio.run(performance_router.export_performance_metrics(current_user=member))

        self.assertEqual(report_error.exception.status_code, 403)
        self.assertEqual(export_error.exception.status_code, 403)

    def test_oidc_admin_can_read_and_export_metrics(self):
        admin = self._user("oidc", "admin")
        monitor = _StubPerformanceMonitor()

        with mock.patch.object(
            performance_router,
            "get_performance_monitor",
            return_value=monitor,
        ), mock.patch.object(
            performance_router.time,
            "time",
            return_value=1234,
        ):
            report = asyncio.run(
                performance_router.get_performance_report(current_user=admin)
            )
            exported = asyncio.run(
                performance_router.export_performance_metrics(current_user=admin)
            )

        self.assertTrue(report["available"])
        self.assertEqual(report["performance_data"]["summary"]["total_files_processed"], 2)
        self.assertEqual(exported.status_code, 200)
        exported_payload = json.loads(exported.body)
        self.assertEqual(
            exported_payload["privacy_scope"],
            "aggregate_only",
        )
        self.assertNotIn("recent_errors", exported_payload["summary"])
        self.assertNotIn("private-filename.pdf", exported.body.decode("utf-8"))
        self.assertIn(
            "performance_export_1234.json",
            exported.headers["content-disposition"],
        )

    def test_local_single_user_mode_receives_aggregate_metrics_only(self):
        monitor = _StubPerformanceMonitor()

        with mock.patch.object(
            performance_router.config,
            "AUTH_PROVIDER",
            "local",
        ), mock.patch.object(
            performance_router,
            "get_performance_monitor",
            return_value=monitor,
        ):
            user = self._user("local")
            report = asyncio.run(
                performance_router.get_performance_report(current_user=user)
            )
            response = asyncio.run(
                performance_router.export_performance_metrics(current_user=user)
            )
            exported = json.loads(response.body)

        self.assertTrue(report["available"])
        self.assertNotIn("recent_errors", report["performance_data"])
        self.assertEqual(exported["privacy_scope"], "aggregate_only")
        self.assertNotIn("recent_errors", exported["summary"])
        self.assertNotIn("sessions", exported)

    def test_multi_user_non_oidc_auth_modes_cannot_read_process_metrics(self):
        for provider in ("supabase", "external_jwt"):
            user = self._user(provider)
            with self.subTest(provider=provider), mock.patch.object(
                performance_router.config,
                "AUTH_PROVIDER",
                provider,
            ):
                with self.assertRaises(HTTPException) as report_error:
                    asyncio.run(
                        performance_router.get_performance_report(current_user=user)
                    )
                with self.assertRaises(HTTPException) as export_error:
                    asyncio.run(
                        performance_router.export_performance_metrics(current_user=user)
                    )

            self.assertEqual(report_error.exception.status_code, 403)
            self.assertEqual(export_error.exception.status_code, 403)

    def test_metrics_export_does_not_reacquire_its_non_reentrant_lock(self):
        monitor = FileProcessingPerformanceMonitor()
        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "metrics.json"
            monitor.export_metrics(str(export_path), last_n_files=5)
            exported = json.loads(export_path.read_text(encoding="utf-8"))

        self.assertEqual(exported["total_sessions"], 0)
        self.assertEqual(exported["sessions"], [])
        self.assertIn("summary", exported)


if __name__ == "__main__":
    unittest.main()
