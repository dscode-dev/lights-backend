from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings
from app.state.playlist_state import get_playlist, save_playlist
from app.state.redis_keys import EVENTS_CHANNEL
from app.state.redis_state import RedisState
from app.services.audio_analyzer import AudioAnalyzer
from app.services.openai_client import OpenAIClient

log = logging.getLogger("youtube.pipeline")


# =========================
# JOB MODEL
# =========================

@dataclass
class AddFromYouTubeJob:
    step_id: str
    title: str
    genre: str
    palette: str
    youtube_url: str
    use_ai: bool = True


# =========================
# PIPELINE
# =========================

class YouTubePipeline:
    def __init__(self, state: RedisState) -> None:
        self.state = state
        self.analyzer = AudioAnalyzer()
        self.ai = OpenAIClient()

        self._queue: asyncio.Queue[AddFromYouTubeJob] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._running = False

    # =========================
    # LIFECYCLE
    # =========================

    async def start(self) -> None:
        if self._running:
            return

        self._running = True
        n = max(1, settings.pipeline_concurrency)

        for i in range(n):
            self._workers.append(asyncio.create_task(self._worker(i)))

        log.info("pipeline_workers_started", extra={"workers": n})

    async def stop(self) -> None:
        self._running = False
        for task in self._workers:
            task.cancel()
        self._workers.clear()
        log.info("pipeline_workers_stopped")

    # =========================
    # PUBLIC API
    # =========================

    async def dispatch(self, job: AddFromYouTubeJob) -> None:
        log.info("pipeline_dispatch_called", extra={"stepId": job.step_id})
        await self._queue.put(job)
        log.info("pipeline_dispatched", extra={"stepId": job.step_id})

    # =========================
    # WORKER
    # =========================

    async def _worker(self, idx: int) -> None:
        log.info("pipeline_worker_up", extra={"worker": idx})

        while self._running:
            job = await self._queue.get()
            try:
                await asyncio.wait_for(
                    self._run_job(job),
                    timeout=settings.pipeline_job_timeout_s,
                )
            except Exception as e:
                log.exception("pipeline_failed", extra={"stepId": job.step_id})
                await self._fail(job.step_id, str(e))
            finally:
                self._queue.task_done()

    # =========================
    # JOB FLOW
    # =========================

    async def _run_job(self, job: AddFromYouTubeJob) -> None:
        log.info("pipeline_started", extra={"stepId": job.step_id})

        await self._progress(job.step_id, 0.1, "download_start")
        audio_path = await self._download_audio(job.youtube_url, job.step_id)
        await self._progress(job.step_id, 0.25, "download_done")

        await self._progress(job.step_id, 0.35, "audio_load")
        analysis = self.analyzer.analyze(audio_path)

        duration_ms = int(analysis["durationMs"])
        bpm = int(analysis["bpm"])
        beat_map = list(analysis["beatMap"])

        await self._progress(job.step_id, 0.6, "audio_done")

        led_plan = None
        if job.use_ai:
            await self._progress(job.step_id, 0.7, "ai_start")
            led_plan = await self.ai.led_plan(
                title=job.title,
                genre=job.genre,
                palette=job.palette,
                duration_ms=duration_ms,
                bpm=bpm,
                beat_map_preview=beat_map,
                topology=self._led_topology(),
            )
            await self._progress(job.step_id, 0.9, "ai_done")

        await self._mark_ready(
            step_id=job.step_id,
            duration_ms=duration_ms,
            bpm=bpm,
            beat_map=beat_map,
            led_plan=led_plan,
        )

        await self._progress(job.step_id, 1.0, "ready")
        log.info("pipeline_completed", extra={"stepId": job.step_id})

    # =========================
    # HELPERS
    # =========================

    async def _download_audio(self, youtube_url: str, step_id: str) -> str:
        os.makedirs(settings.media_dir, exist_ok=True)
        out_path = os.path.join(settings.media_dir, f"{step_id}.wav")

        log.info("audio_download_start", extra={"stepId": step_id})

        subprocess.run(
            [
                "yt-dlp",
                "-x",
                "--audio-format",
                "wav",
                "--no-playlist",
                "--no-cache-dir",
                "-o",
                out_path.replace(".wav", ".%(ext)s"),
                youtube_url,
            ],
            check=True,
        )

        log.info("audio_download_done", extra={"stepId": step_id})
        return out_path

    async def _progress(self, step_id: str, progress: float, stage: str) -> None:
        await self.state.publish_event(
            EVENTS_CHANNEL,
            {
                "type": "playlist_progress",
                "data": {
                    "stepId": step_id,
                    "progress": progress,
                    "stage": stage,
                },
            },
        )

    async def _fail(self, step_id: str, error: str) -> None:
        steps = await get_playlist(self.state)
        for i, s in enumerate(steps):
            if s.id == step_id:
                s.status = "error"
                s.error = error
                s.progress = 1.0
                steps[i] = s
                await save_playlist(self.state, steps)
                await self.state.publish_event(
                    EVENTS_CHANNEL,
                    {"type": "playlist", "data": {"steps": [x.model_dump() for x in steps]}},
                )
                return

    async def _mark_ready(
        self,
        *,
        step_id: str,
        duration_ms: int,
        bpm: int,
        beat_map: list[int],
        led_plan: Optional[dict],
    ) -> None:
        steps = await get_playlist(self.state)
        for i, s in enumerate(steps):
            if s.id == step_id:
                s.status = "ready"
                s.progress = 1.0
                s.durationMs = duration_ms
                s.bpm = bpm
                s.beatMap = beat_map
                s.ledPlan = led_plan
                steps[i] = s
                await save_playlist(self.state, steps)
                await self.state.publish_event(
                    EVENTS_CHANNEL,
                    {"type": "playlist", "data": {"steps": [x.model_dump() for x in steps]}},
                )
                return

    def _led_topology(self) -> dict:
        return {
            "segments": {
                "left": {"vu": {"strips": 4}},
                "right": {"vu": {"strips": 2}},
            }
        }