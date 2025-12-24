from __future__ import annotations

from fastapi import Request, WebSocket

from app.state.redis_state import RedisState
from app.services.playlist_executor import PlaylistExecutor
from app.services.youtube_pipeline import YouTubePipeline
from app.ws.manager import WebSocketManager


# =========================
# CORE STATE
# =========================

def get_state(request: Request) -> RedisState:
    return request.app.state.state


# =========================
# EXECUTOR (HTTP)
# =========================

def get_player_executor(request: Request) -> PlaylistExecutor:
    return request.app.state.executor


# =========================
# PIPELINE
# =========================

def get_pipeline(request: Request) -> YouTubePipeline:
    return request.app.state.pipeline


# =========================
# WS MANAGER
# =========================

def get_ws_manager(request: Request) -> WebSocketManager:
    return request.app.state.ws_manager


def get_ws_manager_ws(websocket: WebSocket) -> WebSocketManager:
    return websocket.app.state.ws_manager


# =========================
# EXECUTOR (WEBSOCKET)
# =========================

def get_player_executor_ws(websocket: WebSocket) -> PlaylistExecutor:
    return websocket.app.state.executor