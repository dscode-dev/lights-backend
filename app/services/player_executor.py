from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, List

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
    - Frontend: status via WS (JSON)
    - ESPs: comandos via WS TEXT
    - LEDs seguem BEATS REAIS do áudio
    """

    LED_TICK_S = 1.0 / 60.0  # 60 FPS p/ precisão visual

    def __init__(self, state, ws, esp_hub):
        self.state = state
        self.ws = ws
        self.esp_hub = esp_hub

        self.is_playing = False
        self.current_index = -1

        self._play_task: Optional[asyncio.Task] = None
        self._start_monotonic: Optional[float] = None

        # Beat real do áudio
        self._beat_map: List[int] = []
        self._beat_idx: int = 0

        # VU físico
        self._vu_max = 50  # hardware maior
        self._vu_peak: float = 0.0

        # Flood control
        self._last_vu_level: Optional[int] = None
        self._last_ct_cmd: Optional[str] = None

        # Contorno
        self._contour_mode: str = "pulse"  # alterna entre pulse / flow

    # =====================================================
    # PLAYER API
    # =====================================================

    async def play(self, index: int):
        self.current_index = index
        self.is_playing = True
        self._start_monotonic = time.monotonic()

        step = await self._get_current_step()
        self._beat_map = step.get("beatMap") or []
        self._beat_idx = 0
        self._vu_peak = 0.0

        await self.ws.broadcast({
            "type": "status",
            "data": {
                "isPlaying": True,
                "activeIndex": index,
            },
        })

        await self._ensure_led_loop_running()
        await self._apply_initial_contour(step)

        log.info(
            "step_start",
            extra={
                "index": index,
                "beats": len(self._beat_map),
            },
        )

    async def pause(self):
        self.is_playing = False

        await self.ws.broadcast({
            "type": "status",
            "data": {"isPlaying": False},
        })

        # zera VU e contorno
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
    # LOOP LED
    # =====================================================

    async def _ensure_led_loop_running(self):
        if self._play_task and not self._play_task.done():
            return
        self._play_task = asyncio.create_task(self._led_loop())

    async def _led_loop(self):
        try:
            while True:
                await asyncio.sleep(self.LED_TICK_S)

                if not self.is_playing:
                    continue

                elapsed = self._elapsed_ms()

                # processa beat real
                await self._process_beats(elapsed)

                # decay contínuo do VU (efeito água)
                self._vu_peak *= 0.88
                level = int(self._vu_peak)

                await self._send_vu(level)

        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("led_loop_failed")

    # =====================================================
    # BEAT ENGINE
    # =====================================================

    async def _process_beats(self, elapsed_ms: int):
        if not self._beat_map:
            return

        if self._beat_idx >= len(self._beat_map):
            return

        next_beat = self._beat_map[self._beat_idx]

        if elapsed_ms < next_beat:
            return

        # 🔥 BEAT REAL DISPAROU 🔥
        self._beat_idx += 1

        # VU ataque forte
        self._vu_peak = float(self._vu_max)

        # alterna modo de contorno
        await self._on_beat_contour()

    async def _on_beat_contour(self):
        """
        Alterna animações do contorno a cada beat
        (o firmware cuida do movimento)
        """
        if self._contour_mode == "pulse":
            self._contour_mode = "flow"
            cmd = "CT:SOLID:180"  # azul/roxo
        else:
            self._contour_mode = "pulse"
            cmd = "CT:SOLID:200"  # roxo mais forte

        await self._send_ct(cmd)

    # =====================================================
    # HELPERS
    # =====================================================

    async def _apply_initial_contour(self, step: dict):
        palette = step.get("palette") or "blue"
        hue = {
            "blue": 160,
            "purple": 200,
            "green": 96,
            "orange": 24,
        }.get(palette, 160)

        await self._send_ct(f"CT:SOLID:{hue}")

    async def _get_current_step(self) -> dict:
        steps = await get_playlist_raw(self.state)
        if not steps:
            return {}
        if self.current_index < 0 or self.current_index >= len(steps):
            return {}
        return steps[self.current_index] or {}

    def _elapsed_ms(self) -> int:
        if not self._start_monotonic:
            return 0
        return int((time.monotonic() - self._start_monotonic) * 1000)

    # =====================================================
    # SENDERS
    # =====================================================

    async def _send_vu(self, level: int):
        level = clamp_int(level, 0, self._vu_max)

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