from __future__ import annotations

import logging
from fastapi import APIRouter, WebSocket, Depends

from app.api.deps import get_ws_manager_ws

log = logging.getLogger("ws")

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    ws_manager=Depends(get_ws_manager_ws),
):
    await ws_manager.connect(websocket)
    log.info("ws_connected_frontend")

    try:
        # ✅ não depende mais do frontend enviar frames.
        while True:
            # Mantém conexão viva, ignora qualquer coisa que venha
            _ = await websocket.receive()
    except Exception:
        log.info("ws_disconnected_frontend")
    finally:
        await ws_manager.disconnect(websocket)
        log.info("ws_disconnected_frontend_cleanup")