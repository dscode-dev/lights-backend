from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import uuid
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings
from app.state.redis_keys import EVENTS_CHANNEL
from app.state.redis_state import RedisState
from app.state.playlist_state import get_playlist, save_playlist
from app.services.audio_analyzer import AudioAnalyzer
from app.services.openai_client import OpenAIClient

log = logging.getLogger("youtube.pipeline")


# =========================
# JOB
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
    def __init__(self, state: RedisState):
        self.state = state
        self.analyzer = AudioAnalyzer()
        self.ai = OpenAIClient()

        self._queue: asyncio.Queue[AddFromYouTubeJob] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._running = False

    async def start(self):
        if self._running:
            return
        self._running = True
        self._workers.append(asyncio.create_task(self._worker()))
        log.info("pipeline_started")

    async def stop(self):
        self._running = False
        for w in self._workers:
            w.cancel()

    async def dispatch(self, job: AddFromYouTubeJob):
        await self._queue.put(job)
        log.info("pipeline_job_queued", extra={"stepId": job.step_id})

    # =========================
    # WORKER
    # =========================

    async def _worker(self):
        while self._running:
            job = await self._queue.get()
            try:
                await self._run_job(job)
            except Exception as e:
                await self._fail(job.step_id, str(e))
                log.exception("pipeline_failed", extra={"stepId": job.step_id})
            finally:
                self._queue.task_done()

    # =========================
    # CORE LOGIC
    # =========================

    async def _run_job(self, job: AddFromYouTubeJob):
        log.info("pipeline_processing", extra={"stepId": job.step_id})

        await self._progress(job.step_id, 0.05, "downloading_audio")

        audio_path = await self._download_audio(job.youtube_url, job.step_id)

        await self._progress(job.step_id, 0.25, "analyzing_audio")

        analysis = self.analyzer.analyze(audio_path)
        duration_ms = int(analysis["durationMs"])

        await self._progress(job.step_id, 0.55, "building_led_plan")

        led_plan = await self._build_led_plan(
            title=job.title,
            genre=job.genre,
            palette=job.palette,
            duration_ms=duration_ms,
            use_ai=job.use_ai,
        )

        await self._progress(job.step_id, 0.9, "finalizing")

        await self._mark_ready(
            step_id=job.step_id,
            duration_ms=duration_ms,
            led_plan=led_plan,
        )

        await self._progress(job.step_id, 1.0, "ready")
        log.info("pipeline_completed", extra={"stepId": job.step_id})

    # =========================
    # LED PLAN
    # =========================

    async def _build_led_plan(
        self,
        *,
        title: str,
        genre: str,
        palette: str,
        duration_ms: int,
        use_ai: bool,
    ) -> dict:
        """
        Plano simples, bonito e determinístico.
        """
        # fallback estável
        base_plan = {
            "presets": {
                "intro": {
                    "id": "intro",
                    "contour": {"mode": "pulse", "hue": 160, "speed": 0.8},
                },
                "main": {
                    "id": "main",
                    "vu": {"level": 22},
                    "contour": {"mode": "solid", "hue": 160},
                },
                "outro": {
                    "id": "outro",
                    "contour": {"mode": "pulse", "hue": 160, "speed": 0.4},
                },
            },
            "timeline": [
                {"from": 0, "to": int(duration_ms * 0.15), "preset": "intro"},
                {"from": int(duration_ms * 0.15), "to": int(duration_ms * 0.9), "preset": "main"},
                {"from": int(duration_ms * 0.9), "to": duration_ms, "preset": "outro"},
            ],
        }

        if not use_ai:
            return base_plan

        try:
            ai_plan = await self.ai.led_plan(
                title=title,
                genre=genre,
                palette=palette,
                duration_ms=duration_ms,
                topology={"simple": True},
            )
            return ai_plan or base_plan
        except Exception:
            log.exception("ai_led_plan_failed")
            return base_plan

    # =========================
    # DOWNLOAD
    # =========================

    async def _download_audio(self, youtube_url: str, step_id: str) -> str:
        os.makedirs(settings.media_dir, exist_ok=True)
        out = os.path.join(settings.media_dir, f"{step_id}.wav")

        cmd = [
            settings.ytdlp_bin,
            "-x",
            "--audio-format", "wav",
            "-o", out,
            youtube_url,
        ]

        log.info("audio_download_start", extra={"stepId": step_id})
        subprocess.run(cmd, check=True)
        log.info("audio_download_done", extra={"stepId": step_id})

        return out

    # =========================
    # REDIS STATE
    # =========================

    async def _mark_ready(self, *, step_id: str, duration_ms: int, led_plan: dict):
        steps = await get_playlist(self.state)
        for i, s in enumerate(steps):
            if s.id == step_id:
                s.status = "ready"
                s.durationMs = duration_ms
                s.ledPlan = led_plan
                steps[i] = s
                await save_playlist(self.state, steps)

                await self.state.publish_event(
                    EVENTS_CHANNEL,
                    {"type": "playlist", "data": {"steps": [x.model_dump() for x in steps]}},
                )
                return

    async def _fail(self, step_id: str, error: str):
        steps = await get_playlist(self.state)
        for i, s in enumerate(steps):
            if s.id == step_id:
                s.status = "error"
                s.error = error
                steps[i] = s
                await save_playlist(self.state, steps)
                await self.state.publish_event(
                    EVENTS_CHANNEL,
                    {"type": "playlist_error", "data": {"stepId": step_id, "error": error}},
                )
                return

    async def _progress(self, step_id: str, progress: float, stage: str):
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