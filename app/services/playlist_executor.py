from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, List, Dict, Any, Set

from app.models.player import PlayerStatus
from app.models.playlist import PlaylistStep
from app.state.redis_state import RedisState
from app.state.redis_keys import EVENTS_CHANNEL
from app.state.playlist_state import get_playlist
from app.state.player_state import get_player_status, save_player_status
from app.core.config import settings
from app.services.esp_client import send_cmd

log = logging.getLogger("player.executor")


class PlaylistExecutor:
    """
    Single-instance player state machine.

    Supports:
      - music: bpm-based beat loop
      - presentation: scripted timeline execution
    """

    def __init__(self, state: RedisState):
        self.state = state
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

        self._last_tick_mono: float = time.monotonic()
        self._beat_accum_s: float = 0.0
        self._status_push_accum_s: float = 0.0

        # presentation runtime
        self._executed_events: Set[int] = set()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._last_tick_mono = time.monotonic()
        self._beat_accum_s = 0.0
        self._status_push_accum_s = 0.0
        self._executed_events.clear()
        self._task = asyncio.create_task(self._run(), name="playlist_executor")
        log.info("executor_started")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3)
            except Exception:
                self._task.cancel()
        log.info("executor_stopped")

    async def _publish_status(self, status: PlayerStatus) -> None:
        await self.state.publish_event(
            EVENTS_CHANNEL,
            {"type": "status", "data": status.model_dump()},
        )

    async def _send_beat(self, step: PlaylistStep) -> None:
        payload = {
            "bpm": step.bpm,
            "palette": step.palette,
            "stepId": step.id,
        }
        for _, ip in settings.esp_registry.items():
            await send_cmd(ip, "beat", payload)

    async def _execute_timeline(
        self,
        step: PlaylistStep,
        elapsed_ms: int,
    ) -> None:
        """
        Execute presentation timeline commands exactly once.
        """
        for idx, item in enumerate(step.esp or []):
            try:
                at_ms = int(item.get("atMs", -1))
                if at_ms < 0:
                    continue

                if idx in self._executed_events:
                    continue

                if elapsed_ms >= at_ms:
                    target = item.get("target")
                    cmd_type = item.get("type")
                    payload = item.get("payload", {})

                    for esp_id, ip in settings.esp_registry.items():
                        if target not in ("broadcast", esp_id):
                            continue
                        await send_cmd(ip, cmd_type, payload)

                    self._executed_events.add(idx)
            except Exception:
                log.exception("timeline_event_error", extra={"stepId": step.id})

    async def _step_duration_ms(self, step: PlaylistStep) -> int:
        if step.durationMs and step.durationMs > 0:
            return step.durationMs
        if step.type == "pause":
            return 3000
        if step.type == "presentation":
            return step.durationMs or 0
        return 0

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                now = time.monotonic()
                dt = now - self._last_tick_mono
                self._last_tick_mono = now

                status = await get_player_status(self.state)
                steps = await get_playlist(self.state)

                if not steps:
                    if status.isPlaying:
                        status.isPlaying = False
                        status.elapsedMs = 0
                        await save_player_status(self.state, status)
                        await self._publish_status(status)
                    await asyncio.sleep(0.2)
                    continue

                if status.activeIndex >= len(steps):
                    status.activeIndex = max(0, len(steps) - 1)

                current = steps[status.activeIndex]

                status.bpm = int(current.bpm or 120)
                status.palette = current.palette
                status.currentTitle = current.title
                status.currentType = current.type

                if status.isPlaying and current.status == "ready":
                    status.elapsedMs += int(dt * 1000)

                    if current.type == "music":
                        bpm = max(30, min(240, status.bpm))
                        beat_interval_s = 60.0 / float(bpm)
                        self._beat_accum_s += dt

                        while self._beat_accum_s >= beat_interval_s:
                            self._beat_accum_s -= beat_interval_s
                            await self._send_beat(current)

                    elif current.type == "presentation":
                        await self._execute_timeline(current, status.elapsedMs)

                    duration_ms = await self._step_duration_ms(current)
                    if duration_ms > 0 and status.elapsedMs >= duration_ms:
                        status.isPlaying = False
                        self._executed_events.clear()

                self._status_push_accum_s += dt
                if status.isPlaying or self._status_push_accum_s >= 0.2:
                    self._status_push_accum_s = 0.0
                    await save_player_status(self.state, status)
                    await self._publish_status(status)

                await asyncio.sleep(0.05)

            except Exception:
                log.exception("executor_loop_error")
                await asyncio.sleep(0.2)
