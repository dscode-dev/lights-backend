# app/services/player_executor.py
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.state.playlist_state import get_playlist_raw

log = logging.getLogger("player.executor")


class PlayerExecutor:
    def __init__(self, state):
        self.state = state
        self._lock = asyncio.Lock()
        self.active_index: Optional[int] = None
        self.is_playing: bool = False

    async def play(self, index: int):
        async with self._lock:
            steps = await get_playlist_raw(self.state)

            if index < 0 or index >= len(steps):
                raise ValueError("Index inválido")

            self.active_index = index
            self.is_playing = True

            log.info("step_start", extra={"index": index})

    async def pause(self):
        async with self._lock:
            self.is_playing = False
            log.info("step_pause")

    async def resume(self):
        async with self._lock:
            if self.active_index is None:
                return
            self.is_playing = True
            log.info("step_resume")

    async def skip(self):
        async with self._lock:
            if self.active_index is None:
                return
            self.active_index += 1
            self.is_playing = False
            log.info("step_skip")

    def snapshot(self):
        return {
            "activeIndex": self.active_index,
            "isPlaying": self.is_playing,
        }