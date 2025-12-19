from __future__ import annotations

from fastapi import Request
from redis.asyncio import Redis
from pymongo.database import Database

from app.state.redis_state import RedisState
from app.ws.manager import WebSocketManager


def get_redis(request: Request) -> Redis:
    return request.app.state.redis  # type: ignore[attr-defined]


def get_mongo_db(request: Request) -> Database:
    return request.app.state.mongo_db  # type: ignore[attr-defined]


def get_state(request: Request) -> RedisState:
    return request.app.state.state  # type: ignore[attr-defined]


def get_ws_manager(request: Request) -> WebSocketManager:
    return request.app.state.ws_manager  # type: ignore[attr-defined]
