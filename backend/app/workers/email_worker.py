"""Poll inbound email and generate reports outside the FastAPI web process."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from app import config


logger = logging.getLogger(__name__)

PollFunction = Callable[[], dict[str, Any]]
ProcessFunction = Callable[[int], Awaitable[dict[str, Any]]]


def write_heartbeat(path: Path | None = None) -> None:
    heartbeat = path or Path(config.EMAIL_WORKER_HEARTBEAT_PATH)
    heartbeat.parent.mkdir(parents=True, exist_ok=True)
    heartbeat.touch()


def heartbeat_is_fresh(path: Path | None = None) -> bool:
    heartbeat = path or Path(config.EMAIL_WORKER_HEARTBEAT_PATH)
    if not heartbeat.is_file():
        return False

    # One report can legitimately spend several minutes in a model call. The
    # container runtime already restarts a crashed process, while this generous
    # threshold still detects a worker that remains hung for an extended time.
    max_age = max(config.EMAIL_WORKER_POLL_INTERVAL_SECONDS * 3, 900)
    return time.time() - heartbeat.stat().st_mtime <= max_age


def _default_graph_poll() -> dict[str, Any]:
    from app.services.microsoft_graph_inbound_service import (
        get_microsoft_graph_inbound_poller,
    )

    return get_microsoft_graph_inbound_poller().poll_messages()


async def _default_process_jobs(max_jobs: int) -> dict[str, Any]:
    # Import lazily so a disabled worker does not initialize document/OCR/model
    # services merely by starting the Compose stack.
    from app.services.email_job_service import get_email_job_service

    return await get_email_job_service().process_pending_jobs(max_jobs=max_jobs)


async def run_cycle(
    *,
    inbound_provider: str | None = None,
    max_jobs: int | None = None,
    graph_poll: PollFunction | None = None,
    process_jobs: ProcessFunction | None = None,
) -> dict[str, Any]:
    """Run one poll-and-process cycle, with injectable functions for tests."""
    provider = inbound_provider or config.INBOUND_EMAIL_PROVIDER
    job_limit = max_jobs or config.EMAIL_WORKER_MAX_JOBS_PER_CYCLE
    poll_summary = None

    if provider == "microsoft_graph":
        poll_summary = (graph_poll or _default_graph_poll)()

    process_summary = await (process_jobs or _default_process_jobs)(job_limit)
    return {
        "inbound_poll": poll_summary,
        "jobs": process_summary,
    }


async def run_forever() -> None:
    config.validate_config()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, stop_event.set)
        except (NotImplementedError, RuntimeError):
            signal.signal(signum, lambda *_args: stop_event.set())

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    write_heartbeat()

    enabled = (
        config.EMAIL_JOB_EXECUTION_MODE == "worker"
        and config.INBOUND_EMAIL_PROVIDER in {"microsoft_graph", "resend"}
    )
    if enabled:
        logger.info(
            "Email worker started: provider=%s interval=%ss max_jobs=%s",
            config.INBOUND_EMAIL_PROVIDER,
            config.EMAIL_WORKER_POLL_INTERVAL_SECONDS,
            config.EMAIL_WORKER_MAX_JOBS_PER_CYCLE,
        )
    else:
        logger.info(
            "Email worker is idle: inbound_provider=%s execution_mode=%s",
            config.INBOUND_EMAIL_PROVIDER,
            config.EMAIL_JOB_EXECUTION_MODE,
        )

    while not stop_event.is_set():
        if enabled:
            try:
                summary = await run_cycle()
                jobs = summary["jobs"]
                if jobs.get("jobs_processed") or (summary["inbound_poll"] or {}).get("accepted"):
                    logger.info("Email worker cycle complete: %s", summary)
            except Exception:
                # Provider outages should be retried without taking down the
                # container or the interactive application.
                logger.exception("Email worker cycle failed; retrying on the next interval")

        write_heartbeat()
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=config.EMAIL_WORKER_POLL_INTERVAL_SECONDS,
            )
        except asyncio.TimeoutError:
            pass

    logger.info("Email worker stopped")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--healthcheck",
        action="store_true",
        help="Exit successfully when the worker heartbeat is current.",
    )
    args = parser.parse_args()

    if args.healthcheck:
        return 0 if heartbeat_is_fresh() else 1

    asyncio.run(run_forever())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
