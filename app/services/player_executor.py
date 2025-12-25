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
    - Recebe frames de áudio do frontend
    - Converte energia em VU realista
    - Envia comandos WS para ESPs
    """

    LED_TICK_S = 1.0 / 60.0  # clock interno (não usado p/ VU, mas mantido)

    def __init__(self, state, ws, esp_hub):
        self.state = state
        self.ws = ws
        self.esp_hub = esp_hub

        self.is_playing = False
        self.current_index = -1

        self._start_monotonic: Optional[float] = None

        # último estado enviado
        self._last_vu_level: Optional[int] = None
        self._last_ct_cmd: Optional[str] = None

        # hardware
        self._vu_max = 50

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

        log.info("executor_play", extra={"index": index})

    async def pause(self):
        self.is_playing = False

        await self.ws.broadcast({
            "type": "status",
            "data": {"isPlaying": False},
        })

        await self._send_vu_energy(0.0)
        await self._send_ct("CT:OFF")

        log.info("executor_pause")

    async def resume(self):
        if self.current_index < 0:
            return

        self.is_playing = True
        self._start_monotonic = time.monotonic()

        await self.ws.broadcast({
            "type": "status",
            "data": {
                "isPlaying": True,
                "activeIndex": self.current_index,
            },
        })

        log.info("executor_resume")

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
    # AUDIO FRAMES (VINDO DO FRONTEND)
    # =====================================================

    async def on_player_audio_frame(
        self,
        *,
        step_index: int,
        elapsed_ms: int,
        energy: float,
        bands: dict | None = None,
        beat: bool = False,
    ):
        """
        Recebe energia REAL do áudio (RMS) vinda do frontend
        """
        if not self.is_playing:
            return

        if step_index != self.current_index:
            return

        log.debug(
            "audio_frame_rx",
            extra={
                "step": step_index,
                "energy": round(energy, 4),
                "elapsed_ms": elapsed_ms,
            },
        )

        await self._send_vu_energy(energy)

        if beat:
            await self._on_beat()

    # =====================================================
    # VU ENGINE (CORRETO)
    # =====================================================

    async def _send_vu_energy(self, energy: float):
        """
        Converte energia real (0..1 RMS) em nível VU perceptual
        """

        # 🔥 ganho agressivo (música baixa reage)
        energy = min(1.0, energy * 4.0)

        # 🔥 curva perceptual (não linear)
        energy = energy ** 0.6

        level = int(energy * self._vu_max)
        level = clamp_int(level, 0, self._vu_max)

        # 🔒 histerese (evita travar quando valor repete)
        if self._last_vu_level is not None:
            if abs(self._last_vu_level - level) < 2:
                return

        self._last_vu_level = level

        cmd = f"VU:{level}"
        self.esp_hub.set_last_vu(cmd)
        await self.esp_hub.broadcast_text(cmd)

        log.debug("vu_tx", extra={"level": level})

    # =====================================================
    # CONTORNO / BEAT
    # =====================================================

    async def _on_beat(self):
        """
        Placeholder para animações de contorno
        """
        await self._send_ct("CT:SOLID:180")

    async def _send_ct(self, cmd: str):
        if self._last_ct_cmd == cmd:
            return

        self._last_ct_cmd = cmd
        self.esp_hub.set_last_ct(cmd)
        await self.esp_hub.broadcast_text(cmd)

        log.debug("ct_tx", extra={"cmd": cmd})