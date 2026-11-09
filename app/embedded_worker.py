"""Opt-in shared-process evaluator for a single-instance free/demo deployment."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.core.config import Settings
from app.runtime import RuntimeResources
from app.worker import EvaluationWorker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def embedded_worker(
    resources: RuntimeResources, settings: Settings
) -> AsyncIterator[asyncio.Task[None] | None]:
    if not settings.embedded_worker_enabled:
        yield None
        return
    stop = asyncio.Event()
    worker = EvaluationWorker(resources.sessions, resources.provider, settings)
    task = asyncio.create_task(worker.run(resources.redis, stop), name="lustcode-evaluator")
    try:
        yield task
    finally:
        # Stop claiming new jobs. A cancelled in-flight job retains its PostgreSQL lease
        # and is recovered by the existing retry protocol after restart.
        stop.set()
        try:
            await asyncio.wait_for(
                asyncio.shield(task), timeout=settings.embedded_worker_shutdown_seconds
            )
        except TimeoutError:
            logger.info("Stopping in-flight embedded evaluation; durable lease will recover")
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        except asyncio.CancelledError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        except Exception:
            logger.exception("Embedded evaluator stopped unexpectedly")
