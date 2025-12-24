from __future__ import annotations

import asyncio
import time
import logging
from typing import Optional, Dict, Any

from app.state.redis_state import RedisState
from app.state.redis_keys import (
    PLAYER_STATUS_KEY,
    PLAYLIST_STEPS_KEY,
    EVENTS_CHANNEL,
)
from app.models.playlist import PlaylistStep
from app.services.esp_udp import EspUdpClient

log = logging.getLogger("player.executor")


def clamp01(v: float) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except Exception:
        return 0.0


class PlaylistExecutor:
    """
    Executor REATIVO:
    - Não gera ritmo fake
    - Não calcula BPM
    - Reage aos frames vindos do frontend (player_audio_frame)
    """

    ESP_LEFT = "192.168.4.102"
    ESP_RIGHT = "192.168.4.101"

    def __init__(self, state):
        # 🔒 blindagem absoluta
        if hasattr(state, "get_json"):
            self.state: RedisState = state
        elif hasattr(state, "state") and hasattr(state.state, "get_json"):
            self.state = state.state
        else:
            raise RuntimeError("PlaylistExecutor recebeu state inválido")

        self.udp = EspUdpClient()

        self._running = False
        self._active_index: Optional[int] = None
        self._started_at: float = 0.0
        self.is_paused: bool = False

        # 🔥 último frame de áudio recebido
        self._last_frame: Optional[Dict[str, Any]] = None

    # =====================================================
    # LIFECYCLE
    # =====================================================

    async def start(self):
        self._running = True
        log.info("executor_started")

    async def stop(self):
        self._running = False

    # =====================================================
    # PLAYER CONTROLS
    # =====================================================

    async def play_index(self, index: int):
        steps = await self._get_steps()
        if index < 0 or index >= len(steps):
            return

        step = steps[index]
        self._active_index = index
        self._started_at = time.monotonic()
        self.is_paused = False
        self._last_frame = None

        await self._send_all_off()

        await self._publish_status(
            isPlaying=True,
            activeIndex=index,
            elapsedMs=0,
            bpm=step.bpm,
            palette=step.palette,
            currentTitle=step.title,
            currentType=step.type,
        )

        log.info("step_start", extra={"stepId": step.id})

    async def pause(self):
        if not self._active_index and self._active_index != 0:
            return
        self.is_paused = True
        await self._publish_status(isPlaying=False)

    async def resume(self):
        if self._active_index is None:
            return
        self.is_paused = False
        await self._publish_status(isPlaying=True)

    async def stop_playback(self):
        await self._send_all_off()
        self._active_index = None
        self._last_frame = None
        await self._publish_status(isPlaying=False, elapsedMs=0)

    # =====================================================
    # 🎧 AUDIO FRAME (VINDO DO FRONTEND)
    # =====================================================

    async def on_player_audio_frame(
        self,
        *,
        step_index: int,
        elapsed_ms: int,
        energy: float,
        bands: Dict[str, float],
        beat: bool,
    ):
        """
        🔥 Este é o coração do sistema.
        Chamado VIA WS pelo frontend.
        """

        if not self._running:
            return

        if self.is_paused:
            return

        if step_index != self._active_index:
            return

        self._last_frame = {
            "energy": clamp01(energy),
            "bands": {
                "bass": clamp01(bands.get("bass", 0)),
                "mid": clamp01(bands.get("mid", 0)),
                "treble": clamp01(bands.get("treble", 0)),
            },
            "beat": bool(beat),
        }

        await self._render_frame(elapsed_ms)

    # =====================================================
    # 🎨 RENDER ENGINE
    # =====================================================

    async def _render_frame(self, elapsed_ms: int):
        if not self._last_frame:
            return

        energy = self._last_frame["energy"]
        bands = self._last_frame["bands"]
        beat = self._last_frame["beat"]

        # ===== VU (reativo de verdade) =====
        vu_left = int(bands["bass"] * 31)
        vu_right = int(bands["mid"] * 50)

        await self._send_vu(vu_left, vu_right)

        # ===== CONTORNO DANÇANTE =====
        if beat:
            hue = self._palette_to_hue("orange")
        else:
            hue = self._palette_to_hue("blue")

        brightness = int(energy * 255)
        await self._send_ct(hue=hue, brightness=brightness)

        await self._publish_status(elapsedMs=elapsed_ms)

    # =====================================================
    # LED IO
    # =====================================================

    async def _send_vu(self, left: int, right: int):
        await self.udp.send(self.ESP_LEFT, f"VU:{left}")
        await self.udp.send(self.ESP_RIGHT, f"VU:{right}")

    async def _send_ct(self, *, hue: int, brightness: int):
        await self.udp.send(self.ESP_LEFT, f"CT:SOLID:{hue}:{brightness}")
        await self.udp.send(self.ESP_RIGHT, f"CT:SOLID:{hue}:{brightness}")

    async def _send_all_off(self):
        await self.udp.send(self.ESP_LEFT, "ALL:OFF")
        await self.udp.send(self.ESP_RIGHT, "ALL:OFF")

    def _palette_to_hue(self, palette: str) -> int:
        return {
            "blue": 160,
            "purple": 200,
            "green": 96,
            "orange": 24,
        }.get(palette, 160)

    # =====================================================
    # STATE
    # =====================================================

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