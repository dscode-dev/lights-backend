from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from redis.asyncio import Redis

from app.ws.manager import WebSocketManager
from app.state.redis_keys import EVENTS_CHANNEL

log = logging.getLogger("ws.broadcaster")


class RedisToWebSocketBroadcaster:
    """
    1) Subscribes to Redis pubsub channel EVENTS_CHANNEL
    2) For each message, broadcasts JSON to all websocket clients
    """

    def __init__(self, redis: Redis, ws_manager: WebSocketManager):
        self.redis = redis
        self.ws_manager = ws_manager
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="redis_ws_broadcaster")
        log.info("broadcaster_started")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3)
            except Exception:
                self._task.cancel()
        log.info("broadcaster_stopped")

    async def _run(self) -> None:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(EVENTS_CHANNEL)
        log.info("subscribed", extra={"channel": EVENTS_CHANNEL})

        try:
            while not self._stop.is_set():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not msg:
                    continue

                data = msg.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8")

                try:
                    payload = json.loads(data)
                except Exception:
                    log.exception("invalid_pubsub_payload", extra={"raw": str(data)[:200]})
                    continue

                await self.ws_manager.broadcast_json(payload)
        finally:
            try:
                await pubsub.unsubscribe(EVENTS_CHANNEL)
                await pubsub.close()
            except Exception:
                pass
