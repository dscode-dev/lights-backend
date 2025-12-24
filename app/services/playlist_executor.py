from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Literal

from app.state.redis_state import RedisState
from app.state.redis_keys import PLAYER_STATUS_KEY, PLAYLIST_STEPS_KEY, EVENTS_CHANNEL
from app.models.playlist import PlaylistStep
from app.services.esp_udp import EspUdpClient

log = logging.getLogger("player.executor")

PlayerState = Literal["idle", "playing", "paused", "ended"]


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


class PlaylistExecutor:
    """
    Executor sincronizado por CLOCK EXTERNO (frontend / YouTube).
    - O backend NÃO mede tempo da música.
    - O backend recebe frames (playerTime real) via WS.
    - A cada frame, calcula VU/contorno e envia para ESPs.
    """

    TICK_HZ = 30  # só para "manter status" ou fallback; LEDs podem ser por frame
    MAX_FRAME_SKEW_S = 2.0  # se ficar muito tempo sem frame, para de animar

    ESP_LEFT = "192.168.137.64"   # VU 0..31 / contorno
    ESP_RIGHT = "192.168.4.101"  # VU 0..50 / contorno

    def __init__(self, state: RedisState):
        self.state = state
        self.udp = EspUdpClient()

        self._task: Optional[asyncio.Task] = None
        self._running = False

        # playback state
        self.is_paused: bool = False
        self._active_index: Optional[int] = None
        self._active_step_id: Optional[str] = None

        # last frame from frontend (clock master)
        self._last_player_time_s: float = 0.0
        self._last_duration_s: float = 0.0
        self._last_player_state: PlayerState = "idle"
        self._last_frame_at_monotonic: float = 0.0

        # cached step
        self._cached_step: Optional[PlaylistStep] = None

        # contorno
        self._last_ct_hue: Optional[int] = None

        # status throttle
        self._last_status_emit_ms: int = 0

    # =========================
    # Lifecycle
    # =========================

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("executor_started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    # =========================
    # Public REST controls
    # =========================

    async def play_index(self, index: int) -> None:
        steps = await self._get_steps()
        if index < 0 or index >= len(steps):
            raise ValueError("Invalid index")

        step = steps[index]
        self._active_index = index
        self._active_step_id = step.id
        self._cached_step = step

        # reset frame tracking
        self.is_paused = False
        self._last_player_state = "playing"
        self._last_player_time_s = 0.0
        self._last_frame_at_monotonic = time.monotonic()
        self._last_ct_hue = None

        # clear LEDs first
        await self._send_ct(off=True)
        await self._send_vu(0, 0)

        # publish initial status
        await self._publish_status(
            isPlaying=True,
            activeIndex=index,
            elapsedMs=0,
            bpm=step.bpm or 120,
            palette=step.palette,
            currentTitle=step.title,
            currentType=step.type,
        )

        log.info("step_start", extra={"stepId": step.id, "index": index})

    async def pause(self) -> None:
        if self._active_index is None:
            return
        self.is_paused = True
        self._last_player_state = "paused"
        await self._publish_status(isPlaying=False)
        log.info("player_paused", extra={"activeIndex": self._active_index})

    async def resume(self) -> None:
        if self._active_index is None:
            return
        self.is_paused = False
        self._last_player_state = "playing"
        await self._publish_status(isPlaying=True)
        log.info("player_resumed", extra={"activeIndex": self._active_index})

    async def stop_playback(self) -> None:
        await self._send_vu(0, 0)
        await self._send_ct(off=True)

        self._active_index = None
        self._active_step_id = None
        self._cached_step = None
        self.is_paused = False

        self._last_player_state = "idle"
        self._last_player_time_s = 0.0
        self._last_duration_s = 0.0
        self._last_frame_at_monotonic = 0.0
        self._last_ct_hue = None

        await self._publish_status(
            isPlaying=False,
            activeIndex=0,
            elapsedMs=0,
            currentTitle="",
            currentType="pause",
        )
        log.info("player_stopped")

    # =========================
    # Clock-master sync (WS)
    # =========================

    async def sync_frame(
        self,
        *,
        step_id: str,
        player_time_s: float,
        duration_s: float,
        state: PlayerState,
    ) -> None:
        """
        Recebe frame REAL do player (YouTube) e atualiza LEDs.
        """
        if self._active_step_id is None:
            return

        # frames de step errado: ignora
        if step_id != self._active_step_id:
            return

        self._last_player_time_s = max(0.0, float(player_time_s))
        self._last_duration_s = max(0.0, float(duration_s))
        self._last_player_state = state
        self._last_frame_at_monotonic = time.monotonic()

        if state == "paused":
            self.is_paused = True
        elif state == "playing":
            self.is_paused = False
        elif state == "ended":
            await self.stop_playback()
            return

        # Atualiza LEDs imediatamente por frame (mais “tempo real”)
        await self._apply_leds_from_time()

        # status (throttle)
        elapsed_ms = int(self._last_player_time_s * 1000)
        now_ms = int(time.time() * 1000)
        if now_ms - self._last_status_emit_ms >= 250:
            self._last_status_emit_ms = now_ms
            await self._publish_status(elapsedMs=elapsed_ms)

    # =========================
    # Internal loop (fallback + safety)
    # =========================

    async def _loop(self) -> None:
        interval = 1 / self.TICK_HZ
        while self._running:
            try:
                # se sem step ativo, dorme
                if self._active_step_id is None:
                    await asyncio.sleep(interval)
                    continue

                # se não chega frame há muito tempo, para de animar (evita lixo)
                if self._last_frame_at_monotonic > 0:
                    age = time.monotonic() - self._last_frame_at_monotonic
                    if age > self.MAX_FRAME_SKEW_S:
                        # mantém status, mas zera LEDs para não ficar travado
                        await self._send_vu(0, 0)
                        await self._send_ct(off=True)
                        await asyncio.sleep(interval)
                        continue

                # se paused, não anima
                if self.is_paused or self._last_player_state != "playing":
                    await asyncio.sleep(interval)
                    continue

                # opcional: tick “extra” (caso frames venham menos que 30Hz)
                await self._apply_leds_from_time()

            except Exception:
                log.exception("executor_loop_error")

            await asyncio.sleep(interval)

    # =========================
    # LED render
    # =========================

    async def _apply_leds_from_time(self) -> None:
        step = await self._get_active_step()
        if step is None:
            return

        elapsed_ms = int(self._last_player_time_s * 1000)

        # ===== VU =====
        bpm = step.bpm or 120
        beat_ms = 60000 / max(1, bpm)
        phase = (elapsed_ms % beat_ms) / beat_ms

        vu_left = clamp(int(phase * 31), 0, 31)
        vu_right = clamp(int(phase * 50), 0, 50)

        await self._send_vu(vu_left, vu_right)

        # ===== CONTORNO (agora “dançante”) =====
        # Em vez de ficar sempre ligado, fazemos um pulso simples no beat:
        # - alterna entre OFF e SOLID conforme fase
        hue = self._palette_to_hue(step.palette)
        pulse_on = phase < 0.45  # janela do pulso
        if pulse_on:
            if hue != self._last_ct_hue:
                await self._send_ct(hue=hue)
                self._last_ct_hue = hue
        else:
            # desliga fora do pulso (sensação de “dança”)
            await self._send_ct(off=True)
            self._last_ct_hue = None

        # auto stop se passar duration (só se tiver)
        if step.durationMs and elapsed_ms >= step.durationMs:
            await self.stop_playback()

    # =========================
    # UDP
    # =========================

    async def _send_vu(self, left: int, right: int) -> None:
        await self.udp.send(self.ESP_LEFT, f"VU:{left}")
        await self.udp.send(self.ESP_RIGHT, f"VU:{right}")

    async def _send_ct(self, *, hue: int | None = None, off: bool = False) -> None:
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

    # =========================
    # State / Steps
    # =========================

    async def _get_steps(self) -> list[PlaylistStep]:
        raw = await self.state.get_json(PLAYLIST_STEPS_KEY) or []
        return [PlaylistStep(**s) for s in raw]

    async def _get_active_step(self) -> Optional[PlaylistStep]:
        if self._cached_step and self._cached_step.id == self._active_step_id:
            return self._cached_step

        steps = await self._get_steps()
        for s in steps:
            if s.id == self._active_step_id:
                self._cached_step = s
                return s
        return None

    # =========================
    # Status publish
    # =========================

    async def _publish_status(self, **fields) -> None:
        status = await self.state.get_json(PLAYER_STATUS_KEY) or {}
        status.update(fields)
        await self.state.set_json(PLAYER_STATUS_KEY, status)
        await self.state.publish_event(EVENTS_CHANNEL, {"type": "status", "data": status})