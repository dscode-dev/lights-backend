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
    TICK_HZ = 30

    ESP_LEFT = "192.168.4.102"  # 4 fitas → 0..31
    ESP_RIGHT = "192.168.4.101"  # 2 fitas → 0..50

    def __init__(self, state: RedisState):
        self.state = state
        self.udp = EspUdpClient()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.is_paused: bool = False
        self._active_index: Optional[int] = None
        self._started_at = 0.0
        self._last_ct_hue: Optional[int] = None
        
    async def _publish_status_safe(self):
        """
        Compat layer: em algumas versões do projeto, o método se chama diferente.
        Aqui tentamos publicar o status sem quebrar.
        """
        # 1) método mais comum em executores
        fn = getattr(self, "emit_status", None)
        if callable(fn):
            await fn()
            return
    
        # 2) nomes alternativos possíveis
        for name in ("publish_status", "_publish_status", "broadcast_status", "_broadcast_status"):
            fn2 = getattr(self, name, None)
            if callable(fn2):
                await fn2()
                return
    
        # 3) fallback: escreve direto no RedisState (se existir)
        # Ajuste os campos conforme seu contrato PlayerStatus
        if hasattr(self, "state") and self.state:
            try:
                await self.state.set_player_status(
                    {
                        "isPlaying": False,
                        "activeIndex": self._active_index if self._active_index is not None else -1,
                        "elapsedMs": int(max(0.0, (asyncio.get_event_loop().time() - self._started_at) * 1000)),
                        "bpm": 0,
                        "palette": "blue",
                        "currentTitle": "",
                        "currentType": "pause",
                    }
                )
            except Exception:
                # não derruba o executor por falha de publish
                log.exception("publish_status_fallback_failed")

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("executor_started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def pause(self):
        if not self._running:
            return

        self.is_paused = True
        await self._publish_status_safe()

    async def resume(self):
        if not self._running:
            return

        if not self.is_paused:
            return

        self.is_paused = False
        await self.emit_status()

    async def play_index(self, index: int):
        steps = await self._get_steps()
        step = steps[index]

        self._active_index = index
        self._started_at = time.monotonic()

        await self._send_ct(off=True)
        await self._send_vu(0, 0)

        await self._publish_status(
            isPlaying=True,
            activeIndex=index,
            elapsedMs=0,
            bpm=step.bpm,
            palette=step.palette,
            currentTitle=step.title,
            currentType=step.type,
        )

        log.info("step_started", extra={"stepId": step.id})

    async def stop_playback(self):
        await self._send_vu(0, 0)
        await self._send_ct(off=True)
        self._active_index = None
        await self._publish_status(isPlaying=False, elapsedMs=0)

    async def _loop(self):
        interval = 1 / self.TICK_HZ

        while self._running:
            try:
                if self.is_paused:
                    await asyncio.sleep(interval)
                    continue

                await self._tick()
            except Exception:
                log.exception("executor_tick_error")

        await asyncio.sleep(interval)

    async def _tick(self) -> None:
        try:
            status = await self.state.get_json(PLAYER_STATUS_KEY)
        except Exception:
            return

        if not status or not status.get("isPlaying"):
            return

        idx = self._active_index
        if idx is None:
            return

        steps = await self._get_steps()
        step = steps[idx]

        elapsed = int((time.monotonic() - self._started_at) * 1000)

        await self._publish_status(elapsedMs=elapsed)

        # ===== VU =====
        bpm = step.bpm or 120
        beat_ms = 60000 / bpm
        phase = (elapsed % beat_ms) / beat_ms

        vu_left = clamp(int(phase * 31), 0, 31)
        vu_right = clamp(int(phase * 50), 0, 50)

        await self._send_vu(vu_left, vu_right)

        # ===== CONTORNO =====
        hue = self._palette_to_hue(step.palette)
        if hue != self._last_ct_hue:
            await self._send_ct(hue=hue)
            self._last_ct_hue = hue

        if step.durationMs and elapsed >= step.durationMs:
            await self.stop_playback()

    async def _send_vu(self, left: int, right: int):
        await self.udp.send(self.ESP_LEFT, f"VU:{left}")
        await self.udp.send(self.ESP_RIGHT, f"VU:{right}")

    async def _send_ct(self, *, hue: int | None = None, off: bool = False):
        if off:
            await self.udp.send(self.ESP_LEFT, "CT:OFF")
            await self.udp.send(self.ESP_RIGHT, "CT:OFF")
        elif hue is not None:
            await self.udp.send(self.ESP_LEFT, f"CT:SOLID:{hue}")
            await self.udp.send(self.ESP_RIGHT, f"CT:SOLID:{hue}")

    def _palette_to_hue(self, palette: str) -> int:
        return {
            "blue": 160,
            "purple": 200,
            "green": 96,
            "orange": 24,
        }.get(palette, 160)

    async def _get_steps(self) -> list[PlaylistStep]:
        raw = await self.state.get_json(PLAYLIST_STEPS_KEY) or []
        return [PlaylistStep(**s) for s in raw]

    async def _publish_status(self, **fields):
        status = await self.state.get_json(PLAYER_STATUS_KEY) or {}
        status.update(fields)
        await self.state.set_json(PLAYER_STATUS_KEY, status)
        await self.state.publish_event(
            EVENTS_CHANNEL, {"type": "status", "data": status}
        )
