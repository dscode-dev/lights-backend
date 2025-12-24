from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("player.executor")


def clamp_int(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


class PlayerExecutor:
    """
    Maestro de LEDs
    - Frontend manda tempo + energia
    - Backend traduz → ESP
    """

    def __init__(self, state, ws, esp_hub):
        self.state = state
        self.ws = ws
        self.esp_hub = esp_hub

        self.is_playing = False
        self.current_index = -1

        # flood control
        self._last_vu: Optional[int] = None
        self._last_ct: Optional[str] = None

        self._vu_max = 50

    # =====================================================
    # RESET LED STATE (🔥 FIX CRÍTICO 🔥)
    # =====================================================

    def _reset_led_state(self):
        self._last_vu = None
        self._last_ct = None

    # =====================================================
    # PLAYER CONTROL
    # =====================================================

    async def play(self, index: int):
        self.current_index = index
        self.is_playing = True

        # 🔥 RESETA ESTADO A CADA PLAY
        self._reset_led_state()

        await self.ws.broadcast({
            "type": "status",
            "data": {
                "isPlaying": True,
                "activeIndex": index,
            },
        })

        # estado inicial explícito
        await self._send_vu(0)
        await self._send_ct("CT:OFF")

    async def pause(self):
        self.is_playing = False

        await self.ws.broadcast({
            "type": "status",
            "data": {"isPlaying": False},
        })

        await self._send_vu(0)
        await self._send_ct("CT:OFF")

    async def next(self):
        steps = await self.state.get_json("playlist:steps") or []
        if not steps:
            return

        next_index = self.current_index + 1
        if next_index >= len(steps):
            next_index = 0

        await self.play(next_index)

    # =====================================================
    # AUDIO FRAME (CORE)
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
        if not self.is_playing:
            return

        if step_index != self.current_index:
            return

        # ===============================
        # VU (sensível até som baixo)
        # ===============================
        vu_level = int((energy ** 0.6) * self._vu_max)
        vu_level = clamp_int(vu_level, 0, self._vu_max)
        await self._send_vu(vu_level)

        # ===============================
        # CONTORNO
        # ===============================
        if energy > 0.05:
            # azul → roxo (sem verde)
            hue = 180 if energy < 0.35 else 200
            await self._send_ct(f"CT:SOLID:{hue}")
        else:
            await self._send_ct("CT:OFF")

    # =====================================================
    # SENDERS
    # =====================================================

    async def _send_vu(self, level: int):
        if self._last_vu == level:
            return
        self._last_vu = level

        cmd = f"VU:{level}"
        self.esp_hub.set_last_vu(cmd)
        await self.esp_hub.broadcast_text(cmd)

    async def _send_ct(self, cmd: str):
        if self._last_ct == cmd:
            return
        self._last_ct = cmd

        self.esp_hub.set_last_ct(cmd)
        await self.esp_hub.broadcast_text(cmd)