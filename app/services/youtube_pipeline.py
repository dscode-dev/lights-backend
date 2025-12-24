from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings
from app.state.redis_state import RedisState
from app.state.playlist_state import (
    upsert_step_by_id,
)
from app.audio.analyzer import analyze_audio_file

log = logging.getLogger("youtube.pipeline")


# ==========================================================
# JOB MODEL
# ==========================================================

@dataclass
class YouTubeJob:
    step_id: str
    youtube_url: str
    title: str
    use_ai: bool


# ==========================================================
# PIPELINE
# ==========================================================

class YouTubePipeline:
    """
    Pipeline responsável por:
    - Baixar áudio do YouTube
    - Analisar áudio (energia, bpm, etc)
    - Atualizar step no Redis
    """

    def __init__(self, state: RedisState):
        self.state = state
        self._queue: asyncio.Queue[YouTubeJob] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._running = False

        self.media_dir = settings.media_dir

    # ======================================================
    # LIFECYCLE
    # ======================================================

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._worker())
        log.info("pipeline_started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    # ======================================================
    # PUBLIC API
    # ======================================================

    async def enqueue(
        self,
        *,
        step_id: str,
        youtube_url: str,
        title: str,
        use_ai: bool = False,
    ):
        job = YouTubeJob(
            step_id=step_id,
            youtube_url=youtube_url,
            title=title,
            use_ai=use_ai,
        )
        await self._queue.put(job)

    # ======================================================
    # WORKER
    # ======================================================

    async def _worker(self):
        while self._running:
            job = await self._queue.get()
            try:
                await asyncio.wait_for(
                    self._run_job(job),
                    timeout=settings.pipeline_job_timeout_s,
                )
            except Exception:
                log.exception("pipeline_failed")
                await upsert_step_by_id(
                    self.state,
                    job.step_id,
                    {
                        "status": "error",
                        "progress": 0,
                    },
                )
            finally:
                self._queue.task_done()

    # ======================================================
    # JOB EXECUTION
    # ======================================================

    async def _run_job(self, job: YouTubeJob):
        step_id = job.step_id

        # 🔽 STATUS: downloading
        await upsert_step_by_id(
            self.state,
            step_id,
            {"status": "downloading", "progress": 0.1},
        )

        # ✅ AQUI ESTAVA O BUG
        audio_path = await self._download_audio(job.youtube_url, step_id)

        # 🔽 STATUS: analyzing
        await upsert_step_by_id(
            self.state,
            step_id,
            {"status": "analyzing", "progress": 0.5},
        )

        analysis = analyze_audio_file(audio_path)

        # 🔽 STATUS: ready
        await upsert_step_by_id(
            self.state,
            step_id,
            {
                "status": "ready",
                "progress": 1.0,
                "audioFile": audio_path,
                "durationMs": analysis.duration_ms,
                "bpm": analysis.bpm,
            },
        )

        log.info("pipeline_completed", extra={"step_id": step_id})

    # ======================================================
    # AUDIO DOWNLOAD
    # ======================================================

    async def _download_audio(self, youtube_url: str, step_id: str) -> str:
        loop = asyncio.get_running_loop()
        os.makedirs(self.media_dir, exist_ok=True)

        output_tpl = f"./media/{step_id}.%(ext)s"
        audio_path = f"./media/{step_id}.wav"

        cmd = [
            "yt-dlp",
            "--no-playlist",
            "-f", "bestaudio",
            "-x",
            "--audio-format", "wav",
            "-o", output_tpl,
            youtube_url,
        ]

        log.info(
            "audio_download_cmd",
            extra={"cmd": " ".join(cmd)},
        )

        def _run():
            return subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

        proc = await loop.run_in_executor(None, _run)

        # ⚠️ NÃO trata warning como erro
        if proc.returncode != 0:
            log.error(
                "audio_download_nonzero_exit",
                extra={
                    "returncode": proc.returncode,
                    "output": proc.stdout,
                },
            )
            raise RuntimeError("yt-dlp falhou ao baixar o áudio")

        if not os.path.exists(audio_path):
            log.error(
                "audio_file_missing",
                extra={"expected": audio_path, "output": proc.stdout},
            )
            raise RuntimeError("Arquivo WAV não encontrado após download")

        log.info(
            "audio_download_ok",
            extra={"path": audio_path},
        )

        return audio_path