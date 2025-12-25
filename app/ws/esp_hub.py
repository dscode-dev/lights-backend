from __future__ import annotations

import asyncio
import logging
from typing import Optional, Set

from starlette.websockets import WebSocket

log = logging.getLogger("esp.ws")


class EspWebSocketHub:
    """
    Hub exclusivo para ESPs.
    - Envia comandos TEXT
    - Stateless (reenvia estado ao reconectar)
    """

    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

        self._last_ct: Optional[str] = None
        self._last_vu: Optional[str] = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

        await self._resend_state(ws)
        log.info("esp_connected", extra={"clients": len(self._clients)})

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        log.info("esp_disconnected", extra={"clients": len(self._clients)})

    async def _resend_state(self, ws: WebSocket) -> None:
        try:
            if self._last_ct:
                await ws.send_text(self._last_ct)
            if self._last_vu:
                await ws.send_text(self._last_vu)
        except Exception:
            pass

    def set_last_ct(self, cmd: str) -> None:
        self._last_ct = cmd

    def set_last_vu(self, cmd: str) -> None:
        self._last_vu = cmd

    async def broadcast_text(self, cmd: str) -> None:
        if not cmd:
            return

        async with self._lock:
            clients = list(self._clients)

        if not clients:
            log.warning(
                "esp_broadcast_no_clients",
                extra={"cmd": cmd},
            )
            return

        log.info(
            "esp_broadcast",
            extra={
                "cmd": cmd,
                "clients": len(clients),
            },
        )

        dead = []
        for ws in clients:
            try:
                await ws.send_text(cmd)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)