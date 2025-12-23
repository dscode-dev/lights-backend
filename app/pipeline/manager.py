import asyncio
import logging
from typing import Optional

log = logging.getLogger("pipeline")


class PipelineManager:
    """
    Responsável por executar pipelines de forma serial/controlada.
    Produção-safe:
    - uma fila
    - execução controlada
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._worker_task = asyncio.create_task(self._worker())
        log.info("pipeline_started")

    async def enqueue(self, coro) -> None:
        await self._queue.put(coro)
        log.info("pipeline_job_enqueued")

    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await job
                log.info("pipeline_job_completed")
            except Exception:
                log.exception("pipeline_job_failed")
            finally:
                self._queue.task_done()