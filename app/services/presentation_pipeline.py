from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict

from app.models.playlist import PlaylistStep
from app.state.playlist_state import get_playlist, save_playlist
from app.state.redis_keys import EVENTS_CHANNEL
from app.state.redis_state import RedisState

log = logging.getLogger("presentation.pipeline")


@dataclass(frozen=True)
class AddPresentationJob:
    step_id: str
    title: str
    genre: str
    palette: str
    audio_path: str
    sequence_path: str


class PresentationPipeline:
    def __init__(self, state: RedisState) -> None:
        self.state = state

    async def run(self, job: AddPresentationJob) -> None:
        log.info(
            '{"level":"INFO","logger":"presentation.pipeline","msg":"pipeline_started","extra":{"stepId":"%s"}}'
            % job.step_id
        )

        await self._progress(job.step_id, 0.20, "loading_files")

        # carrega sequência (JSON)
        with open(job.sequence_path, "r", encoding="utf-8") as f:
            sequence = json.load(f)

        await self._progress(job.step_id, 0.50, "persisting")

        # Atualiza step (ready). Aqui o "durationMs" pode vir do JSON da sequência
        duration_ms = int(sequence.get("durationMs") or 60000)

        await self._set_ready(
            step_id=job.step_id,
            title=job.title,
            genre=job.genre,
            palette=job.palette,
            duration_ms=duration_ms,
            sequence=sequence,
            audio_path=job.audio_path,
        )

        await self._progress(job.step_id, 1.0, "ready")

        log.info(
            '{"level":"INFO","logger":"presentation.pipeline","msg":"pipeline_completed","extra":{"stepId":"%s"}}'
            % job.step_id
        )

    async def _set_ready(
        self,
        *,
        step_id: str,
        title: str,
        genre: str,
        palette: str,
        duration_ms: int,
        sequence: Dict[str, Any],
        audio_path: str,
    ) -> None:
        steps = await get_playlist(self.state)
        idx = next((i for i, s in enumerate(steps) if s.id == step_id), None)
        if idx is None:
            raise RuntimeError("step_not_found")

        step: PlaylistStep = steps[idx]
        step.title = title
        step.genre = genre
        step.palette = palette
        step.type = "presentation"
        step.durationMs = duration_ms
        step.ledPlan = {"presentation": True, "sequence": sequence, "audioPath": audio_path}
        step.status = "ready"
        step.progress = 1.0
        step.error = None

        steps[idx] = step
        await save_playlist(self.state, steps)

        await self.state.publish_event(
            EVENTS_CHANNEL,
            {"type": "playlist", "data": {"steps": [s.model_dump() for s in steps]}},
        )

    async def _progress(self, step_id: str, p: float, stage: str) -> None:
        await self.state.publish_event(
            EVENTS_CHANNEL,
            {"type": "playlist_progress", "data": {"stepId": step_id, "progress": float(p), "stage": stage}},
        )