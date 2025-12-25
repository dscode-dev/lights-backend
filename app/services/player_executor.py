from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, List

from app.state.playlist_state import get_playlist_raw

log = logging.getLogger("player.executor")


def clamp_int(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


class PlayerExecutor:
    """
    Player maestro (produção):
    - Status → frontend (WS JSON)
    - LEDs → ESP (WS TEXT)
    - Envelope REAL do pipeline
    """

    LED_TICK_S = 1.0 / 60.0

    def __init__(self, state, ws, esp_hub):
        self.state = state
        self.ws = ws
        self.esp_hub = esp_hub

        self.is_playing = False
        self.current_index = -1

        self._play_task: Optional[asyncio.Task] = None
        self._start_monotonic: Optional[float] = None

        # Envelope
        self._env: List[float] = []
        self._env_frame_ms = 20

        # Flood control
        self._last_vu_level: Optional[int] = None
        self._last_ct_cmd: Optional[str] = None

        # Hardware
        self._vu_max = 50
        self._vu_headroom = 2
        self._vu_visual_max = self._vu_max - self._vu_headroom

        # VU animation state
        self._vu_mode = "NORMAL"  # NORMAL | IMPACT

        # Contorno cores
        self._ct_hues = [160, 180, 200]
        self._ct_hue_idx = 0

    # =====================================================
    # PLAYER API
    # =====================================================

    async def play(self, index: int):
        self.current_index = index
        self.is_playing = True
        self._start_monotonic = time.monotonic()

        step = await self._get_current_step()

        self._env = list(step.get("energyEnvelope") or [])
        self._env_frame_ms = int(step.get("energyFrameMs") or 20)
        if self._env_frame_ms <= 0:
            self._env_frame_ms = 20

        self._vu_mode = "NORMAL"
        self._ct_hue_idx = 0

        await self.ws.broadcast({
            "type": "status",
            "data": {"isPlaying": True, "activeIndex": index},
        })

        await self._ensure_led_loop_running()
        await self._send_ct("CT:OFF")

        log.info("executor_play", extra={"index": index})

    async def pause(self):
        self.is_playing = False

        await self.ws.broadcast({
            "type": "status",
            "data": {"isPlaying": False},
        })

        await self._send_vu(0)
        await self._send_ct("CT:OFF")

    async def next(self):
        steps = await get_playlist_raw(self.state)
        if not steps:
            return

        idx = (self.current_index + 1) % len(steps)
        await self.pause()
        await self.play(idx)

    # =====================================================
    # LOOP
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

                elapsed_ms = self._elapsed_ms()
                energy = self._energy_at(elapsed_ms)
                await self._apply_energy(energy)

        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("led_loop_failed")

    def _elapsed_ms(self) -> int:
        if not self._start_monotonic:
            return 0
        return int((time.monotonic() - self._start_monotonic) * 1000)

    # =====================================================
    # ENERGY
    # =====================================================

    def _energy_at(self, elapsed_ms: int) -> float:
        if not self._env:
            return 0.0
        frame = int(elapsed_ms / self._env_frame_ms)
        if frame < 0 or frame >= len(self._env):
            return 0.0
        return clamp01(float(self._env[frame]))

    async def _apply_energy(self, energy: float):
        # ===== VU =====
        gain = 1.3
        e = clamp01(energy * gain)

        vu = int(e * self._vu_visual_max)
        vu = clamp_int(vu, 0, self._vu_visual_max)

        await self._send_vu(vu)

        # ===== CONTORNO ACOMPANHA VU =====
        if vu > 0:
            self._ct_hue_idx = (self._ct_hue_idx + 1) % len(self._ct_hues)
            hue = self._ct_hues[self._ct_hue_idx]

            # intensidade implícita via VU (ESP já sabe lidar)
            await self._send_ct(f"CT:SOLID:{hue}")
        else:
            await self._send_ct("CT:OFF")

        # ===== PICO MUITO ALTO → MUDA ANIMAÇÃO DO VU =====
        peak_threshold = int(self._vu_visual_max * 0.85)

        if vu >= peak_threshold and self._vu_mode != "IMPACT":
            self._vu_mode = "IMPACT"
            await self._send_vu_mode("IMPACT")

        elif vu < peak_threshold * 0.6 and self._vu_mode != "NORMAL":
            self._vu_mode = "NORMAL"
            await self._send_vu_mode("NORMAL")

    # =====================================================
    # HELPERS
    # =====================================================

    async def _get_current_step(self) -> dict:
        steps = await get_playlist_raw(self.state)
        if not steps:
            return {}
        if self.current_index < 0 or self.current_index >= len(steps):
            return {}
        return steps[self.current_index] or {}

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

    async def _send_vu_mode(self, mode: str):
        cmd = f"VU_MODE:{mode}"
        await self.esp_hub.broadcast_text(cmd)

    async def _send_ct(self, cmd: str):
        if self._last_ct_cmd == cmd:
            return
        self._last_ct_cmd = cmd

        self.esp_hub.set_last_ct(cmd)
        await self.esp_hub.broadcast_text(cmd)