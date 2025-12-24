# app/api/routes_ws_esp.py
from __future__ import annotations

from fastapi import APIRouter, WebSocket

router = APIRouter(tags=["ws-esp"])


@router.websocket("/ws/esp")
async def ws_esp(websocket: WebSocket):
    hub = getattr(websocket.app.state, "esp_hub", None)
    if hub is None:
        # se não existir, fecha
        await websocket.close()
        return

    await hub.connect(websocket)

    try:
        # ESP não precisa enviar nada, mas a gente mantém o loop pra detectar disconnect.
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        await hub.disconnect(websocket)