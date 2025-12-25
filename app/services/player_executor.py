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
    - Frontend: status via WS (JSON)
    - ESPs: comandos via WS TEXT
    - LEDs seguem envelope REAL do áudio
    """

    LED_TICK_S = 1.0 / 60.0  # 60fps
    VU_HEADROOM = 2          # nunca acender todos os LEDs
    CONTOUR_PULSE_MS = 120   # duração do impacto do beat

    def __init__(self, state, ws, esp_hub):
        self.state = state
        self.ws = ws
        self.esp_hub = esp_hub

        self.is_playing = False
        self.current_index = -1

        self._play_task: Optional[asyncio.Task] = None
        self._start_monotonic: Optional[float] = None

        # Envelope vindo do frontend
        self._last_energy: float = 0.0
        self._last_elapsed_ms: int = 0

        # Flood control
        self._last_vu_level: Optional[int] = None
        self._last_ct_cmd: Optional[str] = None

        # Hardware
        self._vu_max = 50
        self._vu_visual_max = self._vu_max - self.VU_HEADROOM

        # Contorno
        self._last_pulse_at: int = 0
        self._flow_phase: float = 0.0

    # =====================================================
    # PLAYER API
    # =====================================================

    async def play(self, index: int):
        self.current_index = index
        self.is_playing = True
        self._start_monotonic = time.monotonic()

        await self.ws.broadcast({
            "type": "status",
            "data": {
                "isPlaying": True,
                "activeIndex": index,
            },
        })

        await self._ensure_led_loop_running()
        log.info("executor_play", extra={"index": index})

    async def pause(self):
        self.is_playing = False

        await self.ws.broadcast({
            "type": "status",
            "data": {"isPlaying": False},
        })

        await self._send_vu(0)
        await self._send_ct("CT:OFF")

        log.info("executor_pause")

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
    # AUDIO ENVELOPE (VINDO DO FRONTEND)
    # =====================================================

    async def on_player_audio_frame(
        self,
        *,
        step_index: int,
        elapsed_ms: int,
        energy: float,
        beat: bool = False,
        **_,
    ):
        if step_index != self.current_index:
            return

        self._last_energy = max(0.0, min(1.0, float(energy)))
        self._last_elapsed_ms = elapsed_ms

        if beat:
            self._last_pulse_at = elapsed_ms

    # =====================================================
    # LED LOOP
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

                await self._render_vu()
                await self._render_contour()

        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("led_loop_failed")

    # =====================================================
    # VU (COM HEADROOM + COMPRESSÃO)
    # =====================================================

    async def _render_vu(self):
        """
        - Sensível em volumes baixos
        - Compressão suave no topo
        - Nunca acende todos os LEDs
        """
        energy = self._last_energy

        # compressão suave (evita colar no topo)
        compressed = energy ** 0.85

        level = int(compressed * self._vu_visual_max)
        level = clamp_int(level, 0, self._vu_visual_max)

        await self._send_vu(level)

    # =====================================================
    # CONTORNO (FLOW + PULSE)
    # =====================================================

    async def _render_contour(self):
        now = self._last_elapsed_ms

        # ===== PULSE (beat recente)
        if now - self._last_pulse_at < self.CONTOUR_PULSE_MS:
            hue = 200  # roxo / azul forte
            await self._send_ct(f"CT:SOLID:{hue}")
            return

        # ===== FLOW contínuo
        speed = 0.5 + (self._last_energy * 3.0)
        self._flow_phase += speed

        hue = int(160 + (self._flow_phase % 40))  # azul → roxo
        hue = clamp_int(hue, 0, 255)

        await self._send_ct(f"CT:SOLID:{hue}")

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