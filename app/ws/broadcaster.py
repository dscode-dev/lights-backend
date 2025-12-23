from __future__ import annotations

import asyncio
import logging
from redis.asyncio import Redis

from app.ws.manager import WebSocketManager
from app.state.redis_keys import EVENTS_CHANNEL

log = logging.getLogger("ws.broadcaster")


class RedisToWebSocketBroadcaster:
    def __init__(self, redis: Redis, manager: WebSocketManager) -> None:
        self.redis = redis
        self.manager = manager
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("broadcaster_started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
        log.info("broadcaster_stopped")

    async def _loop(self) -> None:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(EVENTS_CHANNEL)
        try:
            while self._running:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not msg:
                    continue
                data = msg.get("data")
                if isinstance(data, (bytes, bytearray)):
                    data = data.decode("utf-8", errors="ignore")
                if isinstance(data, str):
                    await self.manager.broadcast_text(data)
        finally:
            try:
                await pubsub.unsubscribe(EVENTS_CHANNEL)
                await pubsub.close()
            except Exception:
                pass