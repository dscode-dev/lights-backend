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

    # ⚠️ ideal: mover isso pra settings/env, mas vou manter como você fez
    ESP_LEFT = "192.168.137.64"   # 4 fitas → 0..31
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

        self._last_tick_log = 0.0  # evitar flood de log

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
            self._task = None
        log.info("executor_stopped")

    async def pause(self):
        if not self._running:
            return
        self.is_paused = True
        await self._publish_status(isPlaying=False)  # pausa = para o "clock" do show
        log.info("executor_paused", extra={"activeIndex": self._active_index})

    async def resume(self):
        if not self._running:
            return
        if not self.is_paused:
            return
        self.is_paused = False

        # ao retomar, mantém o step atual e reseta started_at para não "pular" tempo
        self._started_at = time.monotonic()

        await self._publish_status(isPlaying=True)
        log.info("executor_resumed", extra={"activeIndex": self._active_index})

    async def play_index(self, index: int):
        steps = await self._get_steps()
        if index < 0 or index >= len(steps):
            log.warning("play_index_out_of_range", extra={"index": index, "len": len(steps)})
            return

        step = steps[index]

        # Se o seu modelo tem status, evita tocar step não pronto
        step_status = getattr(step, "status", None)
        if step_status and step_status not in ("ready", "done"):
            log.warning("play_index_step_not_ready", extra={"index": index, "status": step_status})
            # publica status pra UI não ficar perdida
            await self._publish_status(
                isPlaying=False,
                activeIndex=index,
                elapsedMs=0,
                bpm=getattr(step, "bpm", 120) or 120,
                palette=getattr(step, "palette", "blue") or "blue",
                currentTitle=getattr(step, "title", "") or "",
                currentType=getattr(step, "type", "music") or "music",
            )
            return

        self._active_index = index
        self._started_at = time.monotonic()
        self._last_ct_hue = None  # força enviar CT de novo no primeiro tick

        await self._send_ct(off=True)
        await self._send_vu(0, 0)

        await self._publish_status(
            isPlaying=True,
            activeIndex=index,
            elapsedMs=0,
            bpm=getattr(step, "bpm", 120) or 120,
            palette=getattr(step, "palette", "blue") or "blue",
            currentTitle=getattr(step, "title", "") or "",
            currentType=getattr(step, "type", "music") or "music",
        )

        log.info(
            "step_start",
            extra={
                "stepId": getattr(step, "id", None),
                "index": index,
                "leftIp": self.ESP_LEFT,
                "rightIp": self.ESP_RIGHT,
            },
        )

    async def stop_playback(self):
        await self._send_vu(0, 0)
        await self._send_ct(off=True)

        prev = self._active_index
        self._active_index = None
        self.is_paused = False

        await self._publish_status(isPlaying=False, elapsedMs=0)
        log.info("step_stop", extra={"activeIndex": prev})

    async def _loop(self):
        interval = 1 / self.TICK_HZ
        log.info("executor_loop_up", extra={"tickHz": self.TICK_HZ})

        while self._running:
            try:
                if self.is_paused:
                    await asyncio.sleep(interval)
                    continue

                await self._tick()
                await asyncio.sleep(interval)  # ✅ CRÍTICO: sem isso vira busy-loop
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("executor_tick_error")
                await asyncio.sleep(interval)

        log.info("executor_loop_down")

    async def _tick(self) -> None:
        # lê status do redis (frontend + backend podem atualizar)
        status = await self.state.get_json(PLAYER_STATUS_KEY)
        if not status or not status.get("isPlaying"):
            return

        idx = self._active_index
        if idx is None:
            # Esse log aqui é o "detector" do bug clássico:
            # isPlaying true no redis mas play_index não foi chamado
            now = time.monotonic()
            if now - self._last_tick_log > 2.0:
                self._last_tick_log = now
                log.warning("tick_isPlaying_true_but_no_active_index")
            return

        steps = await self._get_steps()
        if idx < 0 or idx >= len(steps):
            log.warning("tick_active_index_out_of_range", extra={"idx": idx, "len": len(steps)})
            await self.stop_playback()
            return

        step = steps[idx]

        elapsed = int((time.monotonic() - self._started_at) * 1000)

        # publica elapsed pra UI “seguir mais em tempo real”
        await self._publish_status(elapsedMs=elapsed, activeIndex=idx)

        # ===== VU (simples por fase) =====
        bpm = getattr(step, "bpm", 120) or 120
        beat_ms = 60000 / bpm
        phase = (elapsed % beat_ms) / beat_ms

        vu_left = clamp(int(phase * 31), 0, 31)
        vu_right = clamp(int(phase * 50), 0, 50)

        await self._send_vu(vu_left, vu_right)

        # ===== CONTORNO =====
        palette = getattr(step, "palette", "blue") or "blue"
        hue = self._palette_to_hue(palette)
        if hue != self._last_ct_hue:
            await self._send_ct(hue=hue)
            self._last_ct_hue = hue

        # ===== FIM =====
        duration_ms = getattr(step, "durationMs", None)
        if duration_ms and elapsed >= int(duration_ms):
            await self.stop_playback()

        # log leve a cada ~2s
        now = time.monotonic()
        if now - self._last_tick_log > 2.0:
            self._last_tick_log = now
            log.info(
                "tick_ok",
                extra={
                    "idx": idx,
                    "elapsedMs": elapsed,
                    "vuLeft": vu_left,
                    "vuRight": vu_right,
                    "hue": hue,
                },
            )

    async def _send_vu(self, left: int, right: int):
        try:
            await self.udp.send(self.ESP_LEFT, f"VU:{left}")
            await self.udp.send(self.ESP_RIGHT, f"VU:{right}")
        except Exception:
            log.exception("udp_send_vu_failed", extra={"left": left, "right": right})

    async def _send_ct(self, *, hue: int | None = None, off: bool = False):
        try:
            if off:
                await self.udp.send(self.ESP_LEFT, "CT:OFF")
                await self.udp.send(self.ESP_RIGHT, "CT:OFF")
            elif hue is not None:
                await self.udp.send(self.ESP_LEFT, f"CT:SOLID:{hue}")
                await self.udp.send(self.ESP_RIGHT, f"CT:SOLID:{hue}")
        except Exception:
            log.exception("udp_send_ct_failed", extra={"hue": hue, "off": off})

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
        await self.state.publish_event(EVENTS_CHANNEL, {"type": "status", "data": status})