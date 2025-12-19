from __future__ import annotations

import asyncio
from fastapi import WebSocket
from typing import Set


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)

    async def broadcast_json(self, payload: dict) -> None:
        async with self._lock:
            conns = list(self._connections)

        if not conns:
            return

        # send concurrently, drop broken sockets
        async def _send_one(c: WebSocket) -> None:
            try:
                await c.send_json(payload)
            except Exception:
                await self.disconnect(c)

        await asyncio.gather(*[_send_one(c) for c in conns], return_exceptions=True)
