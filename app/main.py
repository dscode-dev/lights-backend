from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from pymongo import MongoClient

from app.core.config import settings
from app.core.logging import setup_logging

from app.state.redis_state import RedisState
from app.state.redis_keys import (
    PLAYLIST_STEPS_KEY,
    PLAYER_STATUS_KEY,
    ESP_NODES_KEY,
    EVENTS_CHANNEL,
)

from app.ws.manager import WebSocketManager
from app.ws.broadcaster import RedisToWebSocketBroadcaster

from app.services.playlist_executor import PlaylistExecutor

# Routers
from app.api.routes_ws import router as ws_router
from app.api.routes_playlist import router as playlist_router
from app.api.routes_status import router as status_router
from app.api.routes_esp import router as esp_router
from app.api.routes_player import router as player_router

log = logging.getLogger("app")


async def bootstrap_defaults(app: FastAPI) -> None:
    state: RedisState = app.state.state  # type: ignore[attr-defined]

    if await state.get_json(PLAYLIST_STEPS_KEY) is None:
        await state.set_json(PLAYLIST_STEPS_KEY, [])
        await state.publish_event(
            EVENTS_CHANNEL,
            {"type": "playlist", "data": {"steps": []}},
        )

    if await state.get_json(PLAYER_STATUS_KEY) is None:
        default_status = {
            "isPlaying": False,
            "activeIndex": 0,
            "elapsedMs": 0,
            "bpm": 120,
            "palette": "blue",
            "currentTitle": "",
            "currentType": "music",
        }
        await state.set_json(PLAYER_STATUS_KEY, default_status)
        await state.publish_event(
            EVENTS_CHANNEL,
            {"type": "status", "data": default_status},
        )

    if await state.get_json(ESP_NODES_KEY) is None:
        await state.set_json(ESP_NODES_KEY, [])
        await state.publish_event(
            EVENTS_CHANNEL,
            {"type": "esp", "data": {"nodes": []}},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    log.info("app_starting", extra={"env": settings.app_env})

    os.makedirs(settings.media_dir, exist_ok=True)

    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    app.state.redis = redis
    app.state.state = RedisState(redis)

    mongo_client = MongoClient(settings.mongo_url)
    app.state.mongo_client = mongo_client
    app.state.mongo_db = mongo_client[settings.mongo_db]

    app.state.ws_manager = WebSocketManager()
    app.state.broadcaster = RedisToWebSocketBroadcaster(redis, app.state.ws_manager)

    await bootstrap_defaults(app)
    await app.state.broadcaster.start()

    app.state.executor = PlaylistExecutor(app.state.state)
    await app.state.executor.start()

    try:
        yield
    finally:
        try:
            await app.state.executor.stop()
        except Exception:
            log.exception("error_stopping_executor")

        try:
            await app.state.broadcaster.stop()
        except Exception:
            log.exception("error_stopping_broadcaster")

        try:
            await redis.close()
        except Exception:
            pass

        try:
            mongo_client.close()
        except Exception:
            pass


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

app.include_router(ws_router)
app.include_router(playlist_router)
app.include_router(status_router)
app.include_router(esp_router)
app.include_router(player_router)


@app.get("/health")
def health():
    return {
        "ok": True,
        "app": settings.app_name,
        "env": settings.app_env,
    }
