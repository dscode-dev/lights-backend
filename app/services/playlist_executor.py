from __future__ import annotations

import asyncio
import time
import logging
from typing import Optional

from app.state.redis_state import RedisState
from app.state.redis_keys import PLAYER_STATUS_KEY, PLAYLIST_STEPS_KEY, EVENTS_CHANNEL
from app.models.playlist import PlaylistStep
from app.services.esp_udp import EspUdpClient

log = logging.getLogger("player.executor")


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


class PlaylistExecutor:
    """
    Executor responsável por:
    - Manter o tempo do show
    - Sincronizar LEDs com BPM / beat
    - Publicar status continuamente
    """

    TICK_HZ = 30  # frequência do loop (30Hz)

    # IPs fixos (por enquanto)
    ESP_LEFT = "192.168.4.102"   # VU esquerdo (0..31)
    ESP_RIGHT = "192.168.4.101"  # VU direito  (0..50)

    def __init__(self, state: RedisState):
        self.state = state
        self.udp = EspUdpClient()

        self._task: Optional[asyncio.Task] = None
        self._running: bool = False
        self.is_paused: bool = False

        self._active_index: Optional[int] = None
        self._started_at: float = 0.0
        self._last_ct_hue: Optional[int] = None

    # =====================================================
    # LIFECYCLE
    # =====================================================

    async def start(self):
        """
        Inicia o loop contínuo do executor.
        Só roda uma vez.
        """
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("executor_started")

    async def stop(self):
        """
        Para completamente o executor.
        """
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

        await self._send_vu(0, 0)
        await self._send_ct(off=True)
        log.info("executor_stopped")

    # =====================================================
    # CONTROLES PÚBLICOS
    # =====================================================

    async def play_index(self, index: int):
        """
        Inicia a execução de um step específico.
        """
        # 🔥 GARANTE QUE O LOOP ESTÁ RODANDO
        if not self._running:
            await self.start()

        steps = await self._get_steps()
        if index < 0 or index >= len(steps):
            return

        step = steps[index]

        self._active_index = index
        self._started_at = time.monotonic()
        self.is_paused = False
        self._last_ct_hue = None

        # reset LEDs
        await self._send_ct(off=True)
        await self._send_vu(0, 0)

        await self._publish_status(
            isPlaying=True,
            activeIndex=index,
            elapsedMs=0,
            bpm=step.bpm or 120,
            palette=step.palette,
            currentTitle=step.title,
            currentType=step.type,
        )

        log.info("step_start", extra={"stepId": step.id})

    async def pause(self):
        if not self._running:
            return

        self.is_paused = True
        await self._publish_status(isPlaying=False)
        log.info("step_paused")

    async def resume(self):
        if not self._running or not self.is_paused:
            return

        self.is_paused = False
        await self._publish_status(isPlaying=True)
        log.info("step_resumed")

    async def stop_playback(self):
        """
        Finaliza o step atual.
        """
        await self._send_vu(0, 0)
        await self._send_ct(off=True)

        self._active_index = None
        self.is_paused = False

        await self._publish_status(
            isPlaying=False,
            elapsedMs=0,
        )

        log.info("step_finished")

    # =====================================================
    # LOOP PRINCIPAL (🔥 AQUI ESTAVA O BUG)
    # =====================================================

    async def _loop(self):
        interval = 1 / self.TICK_HZ
        log.info("executor_loop_started")

        while self._running:
            try:
                if self.is_paused:
                    await asyncio.sleep(interval)
                    continue

                await self._tick()
            except Exception:
                log.exception("executor_tick_error")

            # ⚠️ ESSENCIAL: sleep DENTRO do loop
            await asyncio.sleep(interval)

    async def _tick(self):
        status = await self.state.get_json(PLAYER_STATUS_KEY)
        if not status or not status.get("isPlaying"):
            return

        if self._active_index is None:
            return

        steps = await self._get_steps()
        if self._active_index >= len(steps):
            return

        step = steps[self._active_index]

        elapsed = int((time.monotonic() - self._started_at) * 1000)

        # publica tempo
        await self._publish_status(elapsedMs=elapsed)

        # ==========================
        # VU (beat-based por enquanto)
        # ==========================
        bpm = step.bpm or 120
        beat_ms = 60000 / bpm
        phase = (elapsed % beat_ms) / beat_ms

        vu_left = clamp(int(phase * 31), 0, 31)
        vu_right = clamp(int(phase * 50), 0, 50)

        await self._send_vu(vu_left, vu_right)

        # ==========================
        # CONTORNO (palette)
        # ==========================
        hue = self._palette_to_hue(step.palette)
        if hue != self._last_ct_hue:
            await self._send_ct(hue=hue)
            self._last_ct_hue = hue

        # ==========================
        # FIM DO STEP
        # ==========================
        if step.durationMs and elapsed >= step.durationMs:
            await self.stop_playback()

    # =====================================================
    # LED COMMANDS
    # =====================================================

    async def _send_vu(self, left: int, right: int):
        await self.udp.send(self.ESP_LEFT, f"VU:{left}")
        await self.udp.send(self.ESP_RIGHT, f"VU:{right}")

    async def _send_ct(self, *, hue: Optional[int] = None, off: bool = False):
        if off:
            await self.udp.send(self.ESP_LEFT, "CT:OFF")
            await self.udp.send(self.ESP_RIGHT, "CT:OFF")
        elif hue is not None:
            await self.udp.send(self.ESP_LEFT, f"CT:SOLID:{hue}")
            await self.udp.send(self.ESP_RIGHT, f"CT:SOLID:{hue}")

    # =====================================================
    # STATUS / STATE
    # =====================================================

    async def _publish_status(self, **fields):
        status = await self.state.get_json(PLAYER_STATUS_KEY) or {}
        status.update(fields)

        await self.state.set_json(PLAYER_STATUS_KEY, status)
        await self.state.publish_event(
            EVENTS_CHANNEL,
            {"type": "status", "data": status},
        )

    async def _get_steps(self) -> list[PlaylistStep]:
        raw = await self.state.get_json(PLAYLIST_STEPS_KEY) or []
        return [PlaylistStep(**s) for s in raw]

    # =====================================================
    # UTILS
    # =====================================================

    def _palette_to_hue(self, palette: str) -> int:
        return {
            "blue": 160,
            "purple": 200,
            "green": 96,
            "orange": 24,
        }.get(palette, 160)