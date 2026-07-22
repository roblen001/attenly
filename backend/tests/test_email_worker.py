import asyncio
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("EMAIL_WORKER_POLL_INTERVAL_SECONDS", "30")

from app.workers.email_worker import heartbeat_is_fresh, run_cycle, write_heartbeat


class EmailWorkerCycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_graph_cycle_polls_then_processes_configured_job_limit(self):
        calls = []

        def poll_graph():
            calls.append("poll")
            return {"accepted": 1}

        async def process_jobs(max_jobs):
            calls.append(("process", max_jobs))
            return {"jobs_processed": 1, "jobs_successful": 1}

        result = await run_cycle(
            inbound_provider="microsoft_graph",
            max_jobs=1,
            graph_poll=poll_graph,
            process_jobs=process_jobs,
        )

        self.assertEqual(calls, ["poll", ("process", 1)])
        self.assertEqual(result["inbound_poll"], {"accepted": 1})
        self.assertEqual(result["jobs"]["jobs_successful"], 1)

    async def test_resend_cycle_processes_without_graph_poll(self):
        graph_called = False

        def poll_graph():
            nonlocal graph_called
            graph_called = True
            return {}

        async def process_jobs(max_jobs):
            await asyncio.sleep(0)
            return {"jobs_processed": 0, "limit": max_jobs}

        result = await run_cycle(
            inbound_provider="resend",
            max_jobs=2,
            graph_poll=poll_graph,
            process_jobs=process_jobs,
        )

        self.assertFalse(graph_called)
        self.assertIsNone(result["inbound_poll"])
        self.assertEqual(result["jobs"]["limit"], 2)


class EmailWorkerHeartbeatTests(unittest.TestCase):
    def test_heartbeat_healthcheck_detects_fresh_and_stale_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            heartbeat = Path(temp_dir) / "worker.heartbeat"
            self.assertFalse(heartbeat_is_fresh(heartbeat))

            write_heartbeat(heartbeat)
            self.assertTrue(heartbeat_is_fresh(heartbeat))

            stale_time = time.time() - 901
            os.utime(heartbeat, (stale_time, stale_time))
            self.assertFalse(heartbeat_is_fresh(heartbeat))


if __name__ == "__main__":
    unittest.main()
