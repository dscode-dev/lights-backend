from __future__ import annotations

import json
from typing import Any, Optional
from redis.asyncio import Redis


class RedisState:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def get_json(self, key: str) -> Optional[dict]:
        raw = await self.redis.get(key)
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    async def set_json(self, key: str, value: Any) -> None:
        await self.redis.set(key, json.dumps(value, ensure_ascii=False))

    async def publish_event(self, channel: str, event: dict) -> None:
        await self.redis.publish(channel, json.dumps(event, ensure_ascii=False))
