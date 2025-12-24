# app/ws/esp_hub.py
from __future__ import annotations

import asyncio
import logging
from typing import Optional, Set

from starlette.websockets import WebSocket

log = logging.getLogger("esp.ws")


class EspWebSocketHub:
    """
    Hub exclusivo para ESPs.
    - Só envia TEXT frames (strings)
    - Não usa JSON
    - Não exige ACK
    """

    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

        # estado "stateless" do ESP => backend reenviará após reconnect
        self._last_ct: Optional[str] = None   # ex: "CT:OFF" or "CT:SOLID:160"
        self._last_vu: Optional[str] = None   # ex: "VU:10"

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

        # Reenvia estado atual ao conectar
        await self._resend_state(ws)
        log.info("esp_connected", extra={"clients": len(self._clients)})

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        log.info("esp_disconnected", extra={"clients": len(self._clients)})

    async def _resend_state(self, ws: WebSocket) -> None:
        # O ESP é stateless. Ao reconnect, manda estado completo.
        try:
            if self._last_ct:
                await ws.send_text(self._last_ct)
            if self._last_vu:
                await ws.send_text(self._last_vu)
        except Exception:
            # qualquer falha aqui não pode derrubar nada
            pass

    def set_last_ct(self, cmd: str) -> None:
        self._last_ct = cmd

    def set_last_vu(self, cmd: str) -> None:
        self._last_vu = cmd

    async def broadcast_text(self, cmd: str) -> None:
        """
        Envia exatamente 1 comando por frame.
        cmd precisa ser string sem JSON.
        """
        if not cmd:
            return

        # snapshot pra não segurar lock durante send
        async with self._lock:
            clients = list(self._clients)

        if not clients:
            return

        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_text(cmd)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)