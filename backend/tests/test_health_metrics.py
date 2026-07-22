import asyncio
import unittest

from app.routes.health import metrics_endpoint


class HealthMetricsTests(unittest.TestCase):
    def test_metrics_use_attenly_names_and_process_uptime(self):
        endpoint = getattr(metrics_endpoint, "__wrapped__", metrics_endpoint)
        response = asyncio.run(endpoint(None))
        body = response.body.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "text/plain; version=0.0.4")
        self.assertIn("attenly_health_check", body)
        self.assertIn("attenly_uptime_seconds", body)
        self.assertNotIn("attently_", body)

        uptime_line = next(
            line for line in body.splitlines() if line.startswith("attenly_uptime_seconds ")
        )
        self.assertGreaterEqual(float(uptime_line.split()[1]), 0.0)


if __name__ == "__main__":
    unittest.main()
