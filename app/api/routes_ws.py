from __future__ import annotations

import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from app.api.deps import get_ws_manager
from app.ws.manager import WebSocketManager

log = logging.getLogger("api.ws")

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(
    ws: WebSocket,
    manager: WebSocketManager = Depends(get_ws_manager),
):
    await manager.connect(ws)
    log.info("ws_connected")

    try:
        # Keep the connection alive; we rely on broadcast_json from server side.
        while True:
            # Frontend may send pings or noop; we just consume to keep socket clean.
            # Timeout keeps loop responsive.
            try:
                _ = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # keepalive tick
                await ws.send_json({"type": "ping", "data": {"ok": True}})
    except WebSocketDisconnect:
        log.info("ws_disconnected")
    except Exception:
        log.exception("ws_error")
    finally:
        await manager.disconnect(ws)
