from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, List, Dict

from app.state.playlist_state import get_playlist_raw

log = logging.getLogger("player.executor")


def clamp_int(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


class PlayerExecutor:
    LED_TICK_S = 1.0 / 60.0
    LED_START_DELAY_S = 2.0

    def __init__(self, state, ws, esp_hub):
        self.state = state
        self.ws = ws
        self.esp_hub = esp_hub

        self.is_playing = False
        self.current_index = -1

        self._play_task: Optional[asyncio.Task] = None
        self._start_monotonic: Optional[float] = None
        self._led_start_at: Optional[float] = None

        # Envelope
        self._env: List[float] = []
        self._env_frame_ms = 20

        # Flood control
        self._last_vu_level: Optional[int] = None
        self._last_ct_cmd: Optional[str] = None
        self._last_fx_trig_at = 0.0

        # Hardware
        self._vu_visual_max = 48

        # Contorno
        self._ct_hues = [160, 180, 200]
        self._ct_hue_idx = 0

        # FX
        self._effects: Dict[str, Dict[str, str]] = {}

        # ===== MOCK DRAW STATE =====
        self._draw_on = False
        self._draw_next_eye = 0.0
        self._draw_next_talk = 0.0
        self._draw_eye_state = False
        self._draw_talk_state = False

    # =====================================================
    # PLAYER API
    # =====================================================

    async def play(self, index: int):
        self.current_index = index
        self.is_playing = True

        now = time.monotonic()
        self._start_monotonic = now
        self._led_start_at = now + self.LED_START_DELAY_S
        self._last_fx_trig_at = 0.0

        step = await self._get_current_step()

        self._env = list(step.get("energyEnvelope") or [])
        self._env_frame_ms = int(step.get("energyFrameMs") or 20)
        self._effects = step.get("effects") or {}

        # ===== MOCK DRAW INIT =====
        self._draw_on = True
        self._draw_eye_state = False
        self._draw_talk_state = False
        self._draw_next_eye = now
        self._draw_next_talk = now

        await self.ws.broadcast({
            "type": "status",
            "data": {
                "isPlaying": True,
                "activeIndex": index,
            },
        })

        await self._ensure_led_loop_running()
        await self._send_ct("CT:OFF")
        await self._send_vu(0)

        # liga desenhos
        await self.esp_hub.broadcast_text("FX:DRAW:ON")

        log.info("executor_play", extra={"index": index})

    async def pause(self):
        self.is_playing = False

        await self.ws.broadcast({"type": "status", "data": {"isPlaying": False}})
        await self._send_vu(0)
        await self._send_ct("CT:OFF")

        # desliga desenhos
        await self.esp_hub.broadcast_text("FX:DRAW:OFF")

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

                now = time.monotonic()
                if self._led_start_at and now < self._led_start_at:
                    continue

                elapsed_ms = int((now - self._start_monotonic) * 1000)
                energy = self._energy_at(elapsed_ms)

                await self._apply_energy(energy)
                await self._mock_draw(now, energy)

        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("led_loop_failed")

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
        e = clamp01(energy * 1.25)
        vu = clamp_int(int(e * self._vu_visual_max), 0, self._vu_visual_max)
        await self._send_vu(vu)

        if e > 0.05:
            if e > 0.6:
                self._ct_hue_idx = (self._ct_hue_idx + 1) % len(self._ct_hues)
            hue = self._ct_hues[self._ct_hue_idx]
            await self._send_ct(f"CT:SOLID:{hue}")
        else:
            await self._send_ct("CT:OFF")
            return

        now = time.monotonic()
        if e > 0.55:
            await self._send_fx_trig()
            return

        if e > 0.18 and (now - self._last_fx_trig_at) > 0.16:
            await self._send_fx_trig()

    # =====================================================
    # MOCK DRAW (NOVO)
    # =====================================================

    async def _mock_draw(self, now: float, energy: float):
        if not self._draw_on:
            return

        # olhos piscam aleatoriamente
        if now >= self._draw_next_eye:
            self._draw_eye_state = not self._draw_eye_state
            cmd = "FX:DRAW:EYES:ON" if self._draw_eye_state else "FX:DRAW:EYES:OFF"
            await self.esp_hub.broadcast_text(cmd)
            self._draw_next_eye = now + 0.8

        # boca acompanha energia
        talking = energy > 0.12
        if talking != self._draw_talk_state and now >= self._draw_next_talk:
            self._draw_talk_state = talking
            cmd = "FX:DRAW:TALK:ON" if talking else "FX:DRAW:TALK:OFF"
            await self.esp_hub.broadcast_text(cmd)
            self._draw_next_talk = now + 0.12

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

    async def _send_fx_trig(self):
        self._last_fx_trig_at = time.monotonic()
        await self.esp_hub.broadcast_text("FX:TRIG")

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