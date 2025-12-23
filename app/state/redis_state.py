# app/state/redis_state.py

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from redis.asyncio import Redis
from redis.exceptions import ConnectionError, TimeoutError

from app.core.config import settings

log = logging.getLogger("redis.state")


class RedisState:
    """
    Wrapper único de Redis para o backend.

    - JSON seguro
    - Pub/Sub
    - Logs claros
    - Resiliência a quedas
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    # =========================
    # JSON HELPERS
    # =========================

    async def get_json(self, key: str) -> Optional[Any]:
        try:
            raw = await self.redis.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except (ConnectionError, TimeoutError):
            log.exception("redis_get_json_connection_error", extra={"key": key})
            return None
        except json.JSONDecodeError:
            log.error("redis_get_json_decode_error", extra={"key": key})
            return None

    async def set_json(self, key: str, value: Any) -> None:
        try:
            await self.redis.set(key, json.dumps(value))
        except (ConnectionError, TimeoutError):
            log.exception("redis_set_json_connection_error", extra={"key": key})

    # =========================
    # PUB / SUB
    # =========================

    async def publish_event(self, channel: str, payload: dict) -> None:
        """
        Publica evento para WebSocket / outros consumers
        """
        try:
            await self.redis.publish(channel, json.dumps(payload))
        except (ConnectionError, TimeoutError):
            log.exception(
                "redis_publish_error",
                extra={"channel": channel, "payload": payload},
            )

    # =========================
    # SAFE OPS
    # =========================

    async def exists(self, key: str) -> bool:
        try:
            return bool(await self.redis.exists(key))
        except Exception:
            return False

    async def delete(self, key: str) -> None:
        try:
            await self.redis.delete(key)
        except Exception:
            pass