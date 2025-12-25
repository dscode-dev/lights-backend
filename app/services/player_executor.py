from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from app.state.playlist_state import get_playlist_raw

log = logging.getLogger("player.executor")


def clamp_int(n: int, lo: int, hi: int) -> int:
    if n < lo:
        return lo
    if n > hi:
        return hi
    return n


class PlayerExecutor:
    """
    Player maestro:
    - Recebe frames de áudio do frontend
    - Calcula VU / beats
    - Envia comandos para ESPs via WS TEXT
    """

    LED_TICK_S = 1.0 / 60.0  # alta resolução

    def __init__(self, state, ws, esp_hub):
        self.state = state
        self.ws = ws
        self.esp_hub = esp_hub

        self.is_playing = False
        self.current_index = -1

        self._start_monotonic: Optional[float] = None

        # flood control
        self._last_vu_level: Optional[int] = None
        self._last_ct_cmd: Optional[str] = None

        self._vu_max = 50

        self._last_debug_log = 0.0
        self._contour_toggle = False

    # =====================================================
    # PLAYER API
    # =====================================================

    async def play(self, index: int):
        self.current_index = index
        self.is_playing = True
        self._start_monotonic = time.monotonic()

        log.info(
            "executor_play",
            extra={"index": index},
        )

        await self.ws.broadcast({
            "type": "status",
            "data": {
                "isPlaying": True,
                "activeIndex": index,
            },
        })

    async def pause(self):
        self.is_playing = False

        log.info(
            "executor_pause",
            extra={"index": self.current_index},
        )

        await self.ws.broadcast({
            "type": "status",
            "data": {
                "isPlaying": False,
            },
        })

        await self._send_vu(0)
        await self._send_ct("CT:OFF")

    async def next(self):
        steps = await get_playlist_raw(self.state)
        if not steps:
            return

        idx = self.current_index + 1
        if idx >= len(steps):
            idx = 0

        await self.pause()
        await self.play(idx)

    # =====================================================
    # AUDIO FRAME (DO FRONTEND)
    # =====================================================

    async def on_player_audio_frame(
        self,
        *,
        step_index: int,
        elapsed_ms: int,
        energy: float,
        bands: dict,
        beat: bool,
    ):
        if not self.is_playing:
            return

        vu_level = clamp_int(int(energy * self._vu_max), 0, self._vu_max)

        self._debug_log(
            step=self.current_index,
            elapsed_ms=elapsed_ms,
            energy=round(energy, 3),
            vu=vu_level,
            beat=beat,
        )

        await self._send_vu(vu_level)

        if beat:
            await self._on_beat_contour()

    # =====================================================
    # CONTOUR
    # =====================================================

    async def _on_beat_contour(self):
        self._contour_toggle = not self._contour_toggle

        if self._contour_toggle:
            cmd = "CT:SOLID:180"  # azul/roxo
        else:
            cmd = "CT:OFF"

        await self._send_ct(cmd)

    # =====================================================
    # SENDERS
    # =====================================================

    async def _send_vu(self, level: int):
        if self._last_vu_level == level:
            return
        self._last_vu_level = level

        cmd = f"VU:{level}"
        self.esp_hub.set_last_vu(cmd)
        await self.esp_hub.broadcast_text(cmd)

    async def _send_ct(self, cmd: str):
        if self._last_ct_cmd == cmd:
            return
        self._last_ct_cmd = cmd

        self.esp_hub.set_last_ct(cmd)
        await self.esp_hub.broadcast_text(cmd)

    # =====================================================
    # DEBUG
    # =====================================================

    def _debug_log(self, **data):
        now = time.monotonic()
        if now - self._last_debug_log < 0.5:
            return
        self._last_debug_log = now
        log.info("executor_state", extra=data)