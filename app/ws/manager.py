from typing import Set
from fastapi import WebSocket
import asyncio
import logging

log = logging.getLogger("ws")


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        log.info("ws_connected")

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)
        log.info("ws_disconnected")

    async def broadcast(self, message: dict) -> None:
        async with self._lock:
            dead = []
            for ws in self._connections:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append(ws)

            for ws in dead:
                self._connections.discard(ws)