from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from app.state.redis_state import RedisState
from app.state.redis_keys import PLAYER_STATUS_KEY, PLAYLIST_STEPS_KEY, EVENTS_CHANNEL
from app.models.playlist import PlaylistStep
from app.services.esp_udp import EspUdpClient
from app.services.effects_timeline import EffectsTimeline

log = logging.getLogger("player.executor")


class PlaylistExecutor:
    """
    Executor determinístico de LEDs.
    NÃO calcula BPM.
    NÃO calcula fase.
    Apenas executa o plano (timeline + presets).
    """

    TICK_HZ = 30

    ESP_LEFT = "192.168.4.102"
    ESP_RIGHT = "192.168.4.101"

    def __init__(self, state: RedisState):
        self.state = state
        self.udp = EspUdpClient()

        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._paused = False

        self._active_index: Optional[int] = None
        self._started_at: float = 0.0

        self._timeline: Optional[EffectsTimeline] = None
        self._last_preset_id: Optional[str] = None

    # =====================
    # LIFECYCLE
    # =====================

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
        self._paused = True
        await self._publish_status(isPlaying=False)

    async def resume(self):
        if not self._paused:
            return
        self._paused = False
        await self._publish_status(isPlaying=True)

    # =====================
    # PLAY CONTROL
    # =====================

    async def play_index(self, index: int):
        steps = await self._get_steps()
        step = steps[index]

        if not step.ledPlan:
            log.warning("step_without_led_plan", extra={"stepId": step.id})
            return

        self._active_index = index
        self._started_at = time.monotonic()
        self._paused = False

        self._timeline = EffectsTimeline(
            timeline=step.ledPlan.get("timeline", []),
            presets=step.ledPlan.get("presets", {}),
        )

        self._last_preset_id = None

        await self._clear_leds()

        await self._publish_status(
            isPlaying=True,
            activeIndex=index,
            elapsedMs=0,
            currentTitle=step.title,
            currentType=step.type,
            palette=step.palette,
        )

        log.info("step_start", extra={"stepId": step.id})

    async def stop_playback(self):
        await self._clear_leds()
        self._active_index = None
        self._timeline = None
        await self._publish_status(isPlaying=False)

    # =====================
    # MAIN LOOP
    # =====================

    async def _loop(self):
        interval = 1 / self.TICK_HZ

        while self._running:
            try:
                if self._paused:
                    await asyncio.sleep(interval)
                    continue

                await self._tick()
            except Exception:
                log.exception("executor_tick_error")

            await asyncio.sleep(interval)

    async def _tick(self):
        if self._active_index is None or not self._timeline:
            return

        elapsed_ms = int((time.monotonic() - self._started_at) * 1000)

        await self._publish_status(elapsedMs=elapsed_ms)

        preset = self._timeline.get_active_preset(elapsed_ms)
        if not preset:
            return

        preset_id = preset.get("id")
        if preset_id == self._last_preset_id:
            # preset continua ativo → animação contínua
            await self._apply_preset(preset, elapsed_ms)
            return

        # preset mudou
        self._last_preset_id = preset_id
        log.info(
            "preset_changed",
            extra={
                "preset": preset_id,
                "elapsedMs": elapsed_ms,
            },
        )
        await self._apply_preset(preset, elapsed_ms, reset=True)

    # =====================
    # PRESET EXECUTION
    # =====================

    async def _apply_preset(self, preset: dict, elapsed_ms: int, reset: bool = False):
        """
        Cada preset pode controlar vários segmentos de forma independente.
        """
        if "vu" in preset:
            await self._apply_vu(preset["vu"], elapsed_ms)

        if "contour" in preset:
            await self._apply_contour(preset["contour"], elapsed_ms)

    async def _apply_vu(self, cfg: dict, elapsed_ms: int):
        """
        VU baseado em envelope / curva definida pela IA.
        """
        level = int(cfg.get("level", 0))
        await self.udp.send(self.ESP_LEFT, f"VU:{level}")
        await self.udp.send(self.ESP_RIGHT, f"VU:{level}")

    async def _apply_contour(self, cfg: dict, elapsed_ms: int):
        """
        Contorno animado (pulse, wave, static, etc).
        """
        mode = cfg.get("mode", "solid")

        if mode == "off":
            await self._send_ct(off=True)
            return

        if mode == "solid":
            hue = int(cfg.get("hue", 160))
            await self._send_ct(hue=hue)
            return

        if mode == "pulse":
            speed = float(cfg.get("speed", 1.0))
            hue = int(cfg.get("hue", 160))
            phase = int((elapsed_ms / 1000) * speed) % 2
            if phase == 0:
                await self._send_ct(hue=hue)
            else:
                await self._send_ct(off=True)

    # =====================
    # LED LOW-LEVEL
    # =====================

    async def _send_ct(self, *, hue: int | None = None, off: bool = False):
        if off:
            await self.udp.send(self.ESP_LEFT, "CT:OFF")
            await self.udp.send(self.ESP_RIGHT, "CT:OFF")
        elif hue is not None:
            await self.udp.send(self.ESP_LEFT, f"CT:SOLID:{hue}")
            await self.udp.send(self.ESP_RIGHT, f"CT:SOLID:{hue}")

    async def _clear_leds(self):
        await self._send_ct(off=True)
        await self.udp.send(self.ESP_LEFT, "VU:0")
        await self.udp.send(self.ESP_RIGHT, "VU:0")

    # =====================
    # STATE / REDIS
    # =====================

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