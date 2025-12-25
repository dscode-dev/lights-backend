from __future__ import annotations

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
    - Frontend: status via WS (JSON)
    - ESPs: comandos via WS TEXT
    - Recebe frames do frontend (player_audio_frame) e traduz para VU/CT
    """

    def __init__(self, state, ws, esp_hub):
        self.state = state
        self.ws = ws
        self.esp_hub = esp_hub

        self.is_playing = False
        self.current_index = -1
        self._start_monotonic: Optional[float] = None

        # Flood control
        self._last_vu_level: Optional[int] = None
        self._last_ct_cmd: Optional[str] = None

        # Hardware max (default)
        self._vu_max = 50

        # Debug counters
        self._frames_rx = 0
        self._frames_ignored = 0
        self._frames_applied = 0

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

        log.info("executor_play", extra={"index": index, "vu_max": self._vu_max})

    async def pause(self):
        self.is_playing = False

        await self.ws.broadcast({
            "type": "status",
            "data": {"isPlaying": False},
        })

        await self._send_vu_level(0)
        await self._send_ct("CT:OFF")

        log.info("executor_pause", extra={"index": self.current_index})

    async def resume(self):
        if self.current_index < 0:
            log.warning("executor_resume_no_step")
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

        log.info("executor_resume", extra={"index": self.current_index})

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
        step_index: int | None,
        elapsed_ms: int | None,
        energy: float | None,
        bands: dict | None = None,
        beat: bool = False,
    ):
        """
        Recebe frames do frontend e transforma em VU/CT.

        ✅ Ajuste CRÍTICO:
        - NÃO bloqueia mais por step_index (pra não travar por desencontro)
        - NÃO exige is_playing (porque o áudio pode começar antes do status)
        - Loga motivo exato quando ignora
        """
        self._frames_rx += 1

        if self.current_index < 0:
            self._frames_ignored += 1
            if self._frames_rx % 30 == 0:
                log.warning(
                    "audio_frame_ignored_no_active_step",
                    extra={
                        "rx": self._frames_rx,
                        "ignored": self._frames_ignored,
                        "current_index": self.current_index,
                        "step_index": step_index,
                    },
                )
            return

        # energia inválida vira 0
        e = float(energy or 0.0)
        if e < 0:
            e = 0.0
        if e > 1:
            e = 1.0

        # ✅ ganho forte p/ música baixa
        # - primeiro amplifica
        # - depois curva perceptual
        boosted = min(1.0, e * 6.0)
        perceptual = boosted ** 0.55

        level = int(perceptual * self._vu_max)
        level = clamp_int(level, 0, self._vu_max)

        # ✅ histerese: evita ficar preso em valor (e evita flood)
        if self._last_vu_level is not None and abs(self._last_vu_level - level) < 2:
            # log bem leve
            if self._frames_rx % 60 == 0:
                log.debug(
                    "audio_frame_same_level",
                    extra={
                        "level": level,
                        "energy": round(e, 4),
                        "rx": self._frames_rx,
                    },
                )
            return

        self._frames_applied += 1

        # Logs de tempo real (a cada ~30 frames)
        if self._frames_rx % 30 == 0:
            log.info(
                "audio_frame_apply",
                extra={
                    "rx": self._frames_rx,
                    "applied": self._frames_applied,
                    "ignored": self._frames_ignored,
                    "current_index": self.current_index,
                    "step_index": step_index,
                    "elapsed_ms": elapsed_ms,
                    "energy": round(e, 4),
                    "boosted": round(boosted, 4),
                    "perceptual": round(perceptual, 4),
                    "level": level,
                    "is_playing": self.is_playing,
                },
            )

        await self._send_vu_level(level)

        if beat:
            # opcional: pulsa contorno ao beat
            await self._send_ct("CT:SOLID:180")

    # =====================================================
    # SENDERS
    # =====================================================

    async def _send_vu_level(self, level: int):
        level = clamp_int(int(level), 0, self._vu_max)

        # flood control
        if self._last_vu_level == level:
            return
        self._last_vu_level = level

        cmd = f"VU:{level}"

        # ajuda MUITO: saber se tem ESP conectado
        try:
            esp_count = getattr(self.esp_hub, "clients_count", lambda: -1)()
        except Exception:
            esp_count = -1

        log.debug("vu_tx", extra={"cmd": cmd, "esp_clients": esp_count})

        self.esp_hub.set_last_vu(cmd)
        await self.esp_hub.broadcast_text(cmd)

    async def _send_ct(self, cmd: str):
        if not cmd:
            return

        if self._last_ct_cmd == cmd:
            return
        self._last_ct_cmd = cmd

        self.esp_hub.set_last_ct(cmd)
        await self.esp_hub.broadcast_text(cmd)

        log.debug("ct_tx", extra={"cmd": cmd})