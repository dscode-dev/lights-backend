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

        self._last_ct: Optional[str] = None   # ex: "CT:OFF" or "CT:SOLID:160"
        self._last_vu: Optional[str] = None   # ex: "VU:10"

        # debug
        self._tx_count = 0
        self._tx_drop_no_clients = 0

    def clients_count(self) -> int:
        return len(self._clients)

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
            self._tx_drop_no_clients += 1
            if self._tx_drop_no_clients % 10 == 0:
                log.warning(
                    "esp_tx_drop_no_clients",
                    extra={"drops": self._tx_drop_no_clients, "last_cmd": cmd},
                )
            return

        dead: list[WebSocket] = []
        self._tx_count += 1

        # log leve (a cada 30 sends)
        if self._tx_count % 30 == 0:
            log.info(
                "esp_tx",
                extra={
                    "clients": len(clients),
                    "cmd": cmd,
                    "tx_count": self._tx_count,
                },
            )

        for ws in clients:
            try:
                await ws.send_text(cmd)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)
            log.warning("esp_clients_pruned", extra={"removed": len(dead), "clients": len(self._clients)})