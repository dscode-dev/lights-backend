from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from app.services.youtube_pipeline import YouTubePipeline, AddFromYouTubeJob
from app.services.presentation_pipeline import PresentationPipeline, AddPresentationJob

log = logging.getLogger("pipeline.dispatcher")


@dataclass(frozen=True)
class JobEnvelope:
    job_type: str
    payload: object


class PipelineDispatcher:
    def __init__(self, youtube_pipeline: YouTubePipeline, presentation_pipeline: PresentationPipeline) -> None:
        self.youtube = youtube_pipeline
        self.presentation = presentation_pipeline
        self._q: asyncio.Queue[JobEnvelope] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._worker())
        log.info('{"level":"INFO","logger":"pipeline.dispatcher","msg":"started"}')

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
        log.info('{"level":"INFO","logger":"pipeline.dispatcher","msg":"stopped"}')

    async def dispatch_add_from_youtube(self, job: AddFromYouTubeJob) -> None:
        await self._q.put(JobEnvelope(job_type="add_from_youtube", payload=job))
        log.info(
            '{"level":"INFO","logger":"pipeline.dispatcher","msg":"enqueued","extra":{"type":"add_from_youtube","stepId":"%s"}}'
            % job.step_id
        )

    async def dispatch_add_presentation(self, job: AddPresentationJob) -> None:
        await self._q.put(JobEnvelope(job_type="add_presentation", payload=job))
        log.info(
            '{"level":"INFO","logger":"pipeline.dispatcher","msg":"enqueued","extra":{"type":"add_presentation","stepId":"%s"}}'
            % job.step_id
        )

    async def _worker(self) -> None:
        while self._running:
            env = await self._q.get()
            try:
                if env.job_type == "add_from_youtube":
                    await self.youtube.run(env.payload)  # type: ignore[arg-type]
                elif env.job_type == "add_presentation":
                    await self.presentation.run(env.payload)  # type: ignore[arg-type]
            except Exception as e:
                log.info(
                    '{"level":"ERROR","logger":"pipeline.dispatcher","msg":"job_failed","extra":{"err":"%s"}}'
                    % (str(e).replace('"', "'"))
                )
            finally:
                self._q.task_done()