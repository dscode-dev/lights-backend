# app/services/player_executor.py
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
    Player "maestro":
    - Atualiza status (frontend via ws JSON)
    - Enquanto tocando, envia comandos LED pros ESPs via WS TEXT (strings)
    """

    # frequência VU (30~60 msg/s). 40ms = 25fps, 33ms = 30fps
    LED_TICK_S = 1.0 / 30.0

    def __init__(self, state, ws, esp_hub):
        self.state = state
        self.ws = ws
        self.esp_hub = esp_hub

        self.is_playing = False
        self.current_index = -1

        self._play_task: Optional[asyncio.Task] = None
        self._start_monotonic: Optional[float] = None

        # evita flood
        self._last_vu_level: Optional[int] = None
        self._last_ct_cmd: Optional[str] = None

        # defaults (seu hardware tem variações: 0..50 ou 0..31)
        self._vu_max = 50

    async def play(self, index: int):
        self.current_index = index
        self.is_playing = True
        self._start_monotonic = time.monotonic()

        # Status pro frontend (JSON)
        await self.ws.broadcast({
            "type": "status",
            "data": {
                "isPlaying": True,
                "activeIndex": index,
            },
        })

        # Reinicia loop LED
        await self._ensure_led_loop_running()

        # Ao dar play, reenviar estado base de contorno (se existir) já evita “ESP reconectou e ficou apagado”
        await self._apply_step_initial_led_state()

        log.info("step_start", extra={"index": index})

    async def pause(self):
        self.is_playing = False

        await self.ws.broadcast({
            "type": "status",
            "data": {
                "isPlaying": False,
            },
        })

        # opcional: zera VU ao pausar (firmware stateless)
        await self._send_vu(0)

        log.info("step_pause", extra={"index": self.current_index})

    async def next(self):
        steps = await get_playlist_raw(self.state)
        if not steps:
            return

        next_index = self.current_index + 1
        if next_index >= len(steps):
            next_index = 0

        # pausa => play do próximo
        await self.pause()
        await self.play(next_index)

        log.info("step_next", extra={"index": next_index})

    async def _ensure_led_loop_running(self):
        if self._play_task and not self._play_task.done():
            return
        self._play_task = asyncio.create_task(self._led_loop())

    async def _apply_step_initial_led_state(self):
        """
        Aqui você pode amarrar o CT conforme step/preset.
        Por enquanto: usa palette do step (se existir) e manda CT:SOLID:<hue>.
        Se você quiser CT:OFF em alguns steps, é só condicionar aqui.
        """
        step = await self._get_current_step()
        palette = (step or {}).get("palette") or "blue"

        hue = {
            "blue": 160,
            "purple": 200,
            "green": 96,
            "orange": 24,
        }.get(palette, 160)

        cmd = f"CT:SOLID:{clamp_int(int(hue), 0, 255)}"
        await self._send_ct(cmd)

    async def _get_current_step(self) -> dict:
        steps = await get_playlist_raw(self.state)
        if not steps:
            return {}
        if self.current_index < 0 or self.current_index >= len(steps):
            return {}
        return steps[self.current_index] or {}

    async def _led_loop(self):
        """
        Loop simples e eficaz:
        - roda sempre, mas só envia se is_playing == True
        - manda VU em 30fps, mas só quando muda
        - contorno manda só quando muda (controlado por _send_ct)
        """
        try:
            while True:
                await asyncio.sleep(self.LED_TICK_S)

                if not self.is_playing:
                    continue

                elapsed_ms = self._elapsed_ms()

                # ⚠️ Aqui é onde você pluga seu BeatTracker real / timeline real.
                # Como você ainda vai integrar com LED timeline, vamos manter o VU simples e estável:
                # energia 0..1 baseado em pulso rítmico (bpm) SEM depender do áudio (pra testar LED agora).
                step = await self._get_current_step()
                bpm = int(step.get("bpm") or 120)

                energy = self._pulse_energy(elapsed_ms, bpm)  # 0..1
                level = int(energy * self._vu_max)

                await self._send_vu(level)

        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("led_loop_failed")

    def _elapsed_ms(self) -> int:
        if self._start_monotonic is None:
            return 0
        return int((time.monotonic() - self._start_monotonic) * 1000)

    def _pulse_energy(self, elapsed_ms: int, bpm: int) -> float:
        """
        Energia determinística e boa pra teste de LED (VU).
        Não depende de áudio.
        """
        if bpm <= 0:
            bpm = 120
        beat_ms = int(60000 / bpm)
        phase = elapsed_ms % beat_ms
        window = 140  # janela de impacto do beat

        delta = min(phase, beat_ms - phase)
        if delta > window:
            return 0.0
        return 1.0 - (delta / window)

    async def _send_vu(self, level: int):
        level = clamp_int(int(level), 0, self._vu_max)

        # não floodar
        if self._last_vu_level == level:
            return
        self._last_vu_level = level

        cmd = f"VU:{level}"
        self.esp_hub.set_last_vu(cmd)
        await self.esp_hub.broadcast_text(cmd)

    async def _send_ct(self, cmd: str):
        # não floodar contorno
        if self._last_ct_cmd == cmd:
            return
        self._last_ct_cmd = cmd

        self.esp_hub.set_last_ct(cmd)
        await self.esp_hub.broadcast_text(cmd)