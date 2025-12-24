# app/api/routes_ws.py
from fastapi import APIRouter, WebSocket, Depends
import logging

from app.api.deps import (
    get_player_executor_ws,
    get_ws_manager_ws,
)

log = logging.getLogger("ws")

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    executor = Depends(get_player_executor_ws),
    ws_manager = Depends(get_ws_manager_ws),
):
    await ws_manager.connect(websocket)
    log.info("ws_connected")

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")
            data = msg.get("data") or {}

            # =========================
            # 🎯 CLOCK / AUDIO DO FRONTEND
            # =========================
            if msg_type == "player_audio_frame":
                await executor.on_player_audio_frame(
                    step_index=data.get("stepIndex"),
                    elapsed_ms=data.get("elapsedMs"),
                    energy=data.get("energy"),
                    bands=data.get("bands") or {},
                    beat=bool(data.get("beat")),
                )
                continue

    except Exception:
        log.exception("ws_connection_closed")
    finally:
        await ws_manager.disconnect(websocket)
        log.info("ws_disconnected")