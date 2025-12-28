from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, List, Dict, Any

from app.state.playlist_state import get_playlist_raw

log = logging.getLogger("player.executor")


def clamp_int(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


class PlayerExecutor:
    """
    Player maestro (produção):
    - Status → frontend (WS JSON)
    - LEDs → ESP (WS TEXT)
    - Envelope RMS → VU
    - FX map → coreografia manual
    """

    LED_TICK_S = 1.0 / 60.0
    LED_START_DELAY_S = 2.0

    # ✅ contorno precisa de "evento" (mesmo hue repetido) pra firmware de ondas
    CT_RESEND_MIN_MS = 140  # limite p/ não floodar, mas manter contorno vivo
    CT_ENERGY_MIN = 0.06    # abaixo disso desliga contorno

    # ✅ detector de pico (gera "evento" de contorno)
    PEAK_COOLDOWN_MS = 110

    def __init__(self, state, ws, esp_hub):
        self.state = state
        self.ws = ws
        self.esp_hub = esp_hub

        self.is_playing = False
        self.current_index = -1

        self._play_task: Optional[asyncio.Task] = None
        self._start_monotonic: Optional[float] = None
        self._led_start_at: Optional[float] = None

        # Envelope
        self._env: List[float] = []
        self._env_frame_ms = 20

        # Flood control
        self._last_vu_level: Optional[int] = None
        self._last_ct_cmd: Optional[str] = None
        self._last_fx: Dict[str, str] = {}
        self._last_fx_by_id: Dict[str, str] = {}  # ✅ FX por ID

        # Hardware
        self._vu_max = 50
        self._vu_visual_max = 48

        # Contorno
        self._ct_hues = [160, 180, 200]
        self._ct_hue_idx = 0

        # Effects
        self._effects: Dict[str, Dict[str, str]] = {}
        self._fx_by_id: Dict[str, List[Dict[str, Any]]] = {}  # ✅ NEW

        # Contorno timing / peaks
        self._last_ct_send_ms = -999999
        self._ema = 0.10
        self._floor = 0.05
        self._last_peak_ms = -999999

    # =====================================================
    # PLAYER API
    # =====================================================

    async def play(self, index: int):
        self.current_index = index
        self.is_playing = True

        now = time.monotonic()
        self._start_monotonic = now
        self._led_start_at = now + self.LED_START_DELAY_S

        step = await self._get_current_step()

        self._env = list(step.get("energyEnvelope") or [])
        self._env_frame_ms = int(step.get("energyFrameMs") or 20)
        if self._env_frame_ms <= 0:
            self._env_frame_ms = 20

        # mantém compatível com o que você já tinha
        self._effects = step.get("effects") or {}
        self._last_fx.clear()

        # ✅ FX por ID (novo), sem quebrar nada antigo
        # aceita: step["fxById"] ou step["fx_by_id"]
        self._fx_by_id = step.get("fxById") or step.get("fx_by_id") or {}
        self._last_fx_by_id.clear()

        # reset contorno
        self._last_ct_cmd = None
        self._last_ct_send_ms = -999999
        self._ema = 0.10
        self._floor = 0.05
        self._last_peak_ms = -999999

        await self.ws.broadcast({
            "type": "status",
            "data": {
                "isPlaying": True,
                "activeIndex": index,
            },
        })

        await self._ensure_led_loop_running()

        # estado inicial
        await self._send_ct("CT:OFF", force=True)
        await self._send_vu(0)

        log.info(
            "executor_play",
            extra={
                "index": index,
                "effects": self._effects,
                "fxById": self._fx_by_id,
            },
        )

    async def pause(self):
        self.is_playing = False

        await self.ws.broadcast({
            "type": "status",
            "data": {"isPlaying": False},
        })

        await self._send_vu(0)
        await self._send_ct("CT:OFF", force=True)

    async def next(self):
        steps = await get_playlist_raw(self.state)
        if not steps:
            return

        idx = (self.current_index + 1) % len(steps)
        await self.pause()
        await self.play(idx)

    # =====================================================
    # LOOP
    # =====================================================

    async def _ensure_led_loop_running(self):
        if self._play_task and not self._play_task.done():
            return
        self._play_task = asyncio.create_task(self._led_loop())

    async def _led_loop(self):
        try:
            while True:
                await asyncio.sleep(self.LED_TICK_S)

                if not self.is_playing:
                    continue

                now = time.monotonic()
                if self._led_start_at and now < self._led_start_at:
                    continue

                elapsed_ms = int((now - self._start_monotonic) * 1000)
                energy = self._energy_at(elapsed_ms)

                await self._apply_energy(elapsed_ms, energy)

        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("led_loop_failed")

    # =====================================================
    # ENERGY
    # =====================================================

    def _energy_at(self, elapsed_ms: int) -> float:
        if not self._env:
            return 0.0

        frame = int(elapsed_ms / self._env_frame_ms)
        if frame < 0 or frame >= len(self._env):
            return 0.0

        return clamp01(float(self._env[frame]))

    async def _apply_energy(self, elapsed_ms: int, energy: float):
        # ===== VU =====
        e = clamp01(energy * 1.25)
        vu = clamp_int(int(e * self._vu_visual_max), 0, self._vu_visual_max)
        await self._send_vu(vu)

        # ===== PEAK DETECTOR (gera evento p/ contorno) =====
        # EMA acompanha o "nível médio" e cria threshold dinâmico.
        alpha = 0.08
        self._ema = (1 - alpha) * self._ema + alpha * e
        self._floor = min(self._floor + 0.002, self._ema * 0.85)
        thr = max(0.14, self._ema + 0.10)

        is_peak = (e > thr) and (elapsed_ms - self._last_peak_ms > self.PEAK_COOLDOWN_MS)
        if is_peak:
            self._last_peak_ms = elapsed_ms
            # muda cor em picos (fica vivo)
            self._ct_hue_idx = (self._ct_hue_idx + 1) % len(self._ct_hues)

        # ===== CONTORNO (CORREÇÃO DO "NÃO RECEBE NADA") =====
        # O firmware de ondas precisa receber "CT:SOLID" repetidamente (evento),
        # mesmo com o MESMO hue, senão ele spawna uma onda só e morre.
        if e > self.CT_ENERGY_MIN:
            hue = self._ct_hues[self._ct_hue_idx]
            cmd = f"CT:SOLID:{hue}"

            # força reenvio em:
            # - pico (evento)
            # - ou a cada CT_RESEND_MIN_MS pra manter ondas nascendo
            force = False
            if is_peak:
                force = True
            elif (elapsed_ms - self._last_ct_send_ms) >= self.CT_RESEND_MIN_MS:
                force = True

            await self._send_ct(cmd, force=force, elapsed_ms=elapsed_ms)

            # ✅ também envia trigger explícito pra firmwares que suportam (2x VU+contorno tem FX:TRIG)
            # isso não quebra quem ignora.
            if is_peak:
                await self._send_fx_cmd("FX:TRIG", fx_id="ct_trig")
        else:
            await self._send_ct("CT:OFF", force=False, elapsed_ms=elapsed_ms)

        # ===== FX MAP (antigo: group->mode) =====
        if self._effects:
            bucket = "high" if e > 0.55 else "default"
            fx = self._effects.get(bucket) or {}

            for group, mode in fx.items():
                if self._last_fx.get(group) == mode:
                    continue

                self._last_fx[group] = mode
                cmd = f"FX:{group.upper()}:{mode.upper()}"
                await self._send_fx_cmd(cmd, fx_id=f"group:{group}")

                log.info(
                    "fx_change",
                    extra={
                        "group": group,
                        "mode": mode,
                        "energy": round(e, 3),
                    },
                )

        # ===== FX POR ID (novo: permite FX:FLAKE_ROTATE etc) =====
        # Estrutura esperada no step:
        #   "fxById": {
        #       "default": [{"id":"flake_rotate","cmd":"FX:FLAKE_ROTATE"}],
        #       "high":    [{"id":"flake_burst","cmd":"FX:FLAKE_BURST"}]
        #   }
        if self._fx_by_id:
            bucket2 = "high" if e > 0.55 else "default"
            items = list(self._fx_by_id.get(bucket2) or [])

            # opcional: "always" roda junto (não obrigatório)
            items += list(self._fx_by_id.get("always") or [])

            for it in items:
                if not isinstance(it, dict):
                    continue
                fx_id = str(it.get("id") or "").strip()
                cmd = str(it.get("cmd") or "").strip()

                if not cmd:
                    continue

                # se não vier id, usa o cmd como id (ainda dedupa)
                if not fx_id:
                    fx_id = f"cmd:{cmd}"

                # dedupe por ID (não flood)
                if self._last_fx_by_id.get(fx_id) == cmd:
                    continue

                self._last_fx_by_id[fx_id] = cmd
                await self._send_fx_cmd(cmd, fx_id=fx_id)

                log.info(
                    "fx_id_send",
                    extra={
                        "id": fx_id,
                        "cmd": cmd,
                        "bucket": bucket2,
                        "energy": round(e, 3),
                    },
                )

    # =====================================================
    # HELPERS
    # =====================================================

    async def _get_current_step(self) -> dict:
        steps = await get_playlist_raw(self.state)
        if not steps:
            return {}
        if self.current_index < 0 or self.current_index >= len(steps):
            return {}
        return steps[self.current_index] or {}

    # =====================================================
    # SENDERS
    # =====================================================

    async def _send_vu(self, level: int):
        if self._last_vu_level == level:
            return
        self._last_vu_level = level

        cmd = f"VU:{level}"
        self.esp_hub.set_last_vu(cmd)
        await self.esp_hub.broadcast_text(cmd)

    async def _send_ct(self, cmd: str, *, force: bool = False, elapsed_ms: int = 0):
        # ✅ correção: permitir reenvio do MESMO CT:SOLID pra gerar novas ondas
        if not force and self._last_ct_cmd == cmd:
            return

        # rate-limit de reenvio (mesmo forçado)
        if force and (elapsed_ms - self._last_ct_send_ms) < self.CT_RESEND_MIN_MS:
            # ainda atualiza o "last" se for mudança real
            if self._last_ct_cmd != cmd:
                self._last_ct_cmd = cmd
                self.esp_hub.set_last_ct(cmd)
                await self.esp_hub.broadcast_text(cmd)
            return

        self._last_ct_cmd = cmd
        self._last_ct_send_ms = elapsed_ms

        self.esp_hub.set_last_ct(cmd)
        await self.esp_hub.broadcast_text(cmd)

    async def _send_fx_cmd(self, cmd: str, *, fx_id: str):
        # ✅ dedupe leve por id+cmd (não remove nada existente)
        prev = self._last_fx_by_id.get(fx_id)
        if prev == cmd:
            return
        self._last_fx_by_id[fx_id] = cmd

        await self.esp_hub.broadcast_text(cmd)