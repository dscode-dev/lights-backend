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


def clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


class PlayerExecutor:
    """
    Player maestro (produção):
    - Status pro frontend via WS JSON (ws_manager)
    - LEDs pros ESP via WS TEXT (esp_hub)
    - Energia REAL vem do envelope calculado no pipeline (energyEnvelope)
    """

    LED_TICK_S = 1.0 / 60.0  # 60fps
    CT_PULSE_MS = 90         # duração do "flash" no contorno ao detectar pico

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
        self._env_frame_ms: int = 20

        # Flood control
        self._last_vu_level: Optional[int] = None
        self._last_ct_cmd: Optional[str] = None

        # hardware
        self._vu_max = 50

        # Pico/beat detector (dinâmico)
        self._floor = 0.05
        self._ema = 0.10
        self._last_peak_ms = -999999
        self._ct_off_at_ms = -1

        # cor base do contorno (azul/roxo)
        self._ct_hues = [160, 180, 200]  # blue -> lilac -> purple
        self._ct_hue_idx = 0

    # =====================================================
    # PLAYER API
    # =====================================================

    async def play(self, index: int):
        self.current_index = index
        self.is_playing = True
        self._start_monotonic = time.monotonic()

        step = await self._get_current_step()

        # ✅ carrega envelope (se existir)
        self._env = list(step.get("energyEnvelope") or [])
        self._env_frame_ms = int(step.get("energyFrameMs") or 20)
        if self._env_frame_ms <= 0:
            self._env_frame_ms = 20

        # reset detector
        self._floor = 0.05
        self._ema = 0.10
        self._last_peak_ms = -999999
        self._ct_off_at_ms = -1

        await self.ws.broadcast({
            "type": "status",
            "data": {
                "isPlaying": True,
                "activeIndex": index,
            },
        })

        await self._ensure_led_loop_running()

        # contorno inicia OFF (pra não ficar sempre aceso)
        await self._send_ct("CT:OFF")

        log.info(
            "executor_play",
            extra={
                "index": index,
                "env_len": len(self._env),
                "env_frame_ms": self._env_frame_ms,
            },
        )

    async def pause(self):
        self.is_playing = False

        await self.ws.broadcast({
            "type": "status",
            "data": {"isPlaying": False},
        })

        await self._send_vu(0)
        await self._send_ct("CT:OFF")

        log.info("executor_pause", extra={"index": self.current_index})

    async def next(self):
        steps = await get_playlist_raw(self.state)
        if not steps:
            return

        idx = self.current_index + 1
        if idx >= len(steps):
            idx = 0

        await self.pause()
        await self.play(idx)

        log.info("executor_next", extra={"index": idx})

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

                elapsed_ms = self._elapsed_ms()

                energy = self._energy_at(elapsed_ms)  # 0..1
                await self._apply_energy(elapsed_ms, energy)

        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("led_loop_failed")

    def _elapsed_ms(self) -> int:
        if not self._start_monotonic:
            return 0
        return int((time.monotonic() - self._start_monotonic) * 1000)

    # =====================================================
    # ENERGY ENGINE
    # =====================================================

    def _energy_at(self, elapsed_ms: int) -> float:
        if not self._env:
            return 0.0

        frame = int(elapsed_ms / self._env_frame_ms)
        if frame < 0:
            return 0.0
        if frame >= len(self._env):
            # acabou o envelope
            return 0.0

        return clamp01(float(self._env[frame]))

    async def _apply_energy(self, elapsed_ms: int, energy: float):
        # 1) VU: usa energia contínua
        # dá um ganho leve p/ músicas baixas
        gain = 1.35
        e = clamp01(energy * gain)

        vu = int(e * self._vu_max)
        await self._send_vu(vu)

        # 2) Detector de pico sensível (dinâmico)
        # EMA acompanha "média" e floor acompanha ruído.
        alpha = 0.08
        self._ema = (1 - alpha) * self._ema + alpha * e
        self._floor = min(self._floor + 0.002, self._ema * 0.85)

        # threshold: acima da média + margem
        thr = max(0.14, self._ema + 0.10)

        # cooldown evita flood de CT
        cooldown_ms = 90

        is_peak = (e > thr) and (elapsed_ms - self._last_peak_ms > cooldown_ms)

        if is_peak:
            self._last_peak_ms = elapsed_ms

            # alterna azul/roxo (sem verde)
            self._ct_hue_idx = (self._ct_hue_idx + 1) % len(self._ct_hues)
            hue = self._ct_hues[self._ct_hue_idx]

            await self._send_ct(f"CT:SOLID:{hue}")
            self._ct_off_at_ms = elapsed_ms + self.CT_PULSE_MS

            log.info(
                "led_peak",
                extra={
                    "elapsed_ms": elapsed_ms,
                    "energy": round(e, 3),
                    "thr": round(thr, 3),
                    "vu": vu,
                    "hue": hue,
                },
            )

        # desliga contorno após pulso (mantém “batendo”)
        if self._ct_off_at_ms > 0 and elapsed_ms >= self._ct_off_at_ms:
            self._ct_off_at_ms = -1
            await self._send_ct("CT:OFF")

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
        level = clamp_int(level, 0, self._vu_max)

        # anti-flood: só envia se mudou
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