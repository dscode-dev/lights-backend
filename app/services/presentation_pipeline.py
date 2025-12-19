from __future__ import annotations

import json
import logging
import os
from typing import Dict, Any

from app.models.playlist import PlaylistStep
from app.state.redis_state import RedisState
from app.state.redis_keys import EVENTS_CHANNEL
from app.state.playlist_state import get_playlist, save_playlist
from app.services.audio_analysis import analyze_audio

log = logging.getLogger("pipeline.presentation")


class PresentationPipeline:
    def __init__(self, state: RedisState):
        self.state = state

    async def run(
        self,
        step_id: str,
        title: str,
        palette: str,
        genre: str,
        audio_path: str,
        sequence: Dict[str, Any],
    ):
        try:
            duration_ms, bpm = analyze_audio(audio_path)

            def apply_ready(step: PlaylistStep) -> PlaylistStep:
                step.status = "ready"
                step.progress = 1.0
                step.trackTitle = title
                step.audioFile = audio_path
                step.durationMs = duration_ms
                step.bpm = bpm
                step.palette = palette
                step.genre = genre

                # sequência fechada
                step.leds = "custom_sequence"
                step.portal = "custom_sequence"
                step.hologram = "custom_sequence"
                step.esp = sequence.get("timeline", [])

                return step

            steps = await get_playlist(self.state)
            for i, s in enumerate(steps):
                if s.id == step_id:
                    steps[i] = apply_ready(s)
                    break

            await save_playlist(self.state, steps)

            await self.state.publish_event(
                EVENTS_CHANNEL,
                {
                    "type": "playlist_ready",
                    "data": {"step": steps[i].model_dump()},
                },
            )

            log.info("presentation_ready", extra={"stepId": step_id})

        except Exception as e:
            log.exception("presentation_pipeline_error")

            await self.state.publish_event(
                EVENTS_CHANNEL,
                {
                    "type": "playlist_error",
                    "data": {"stepId": step_id, "error": str(e)},
                },
            )
