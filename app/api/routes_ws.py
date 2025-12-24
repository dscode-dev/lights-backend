from fastapi import APIRouter, WebSocket, Depends
import asyncio
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
    executor=Depends(get_player_executor_ws),
    ws_manager=Depends(get_ws_manager_ws),
):
    await ws_manager.connect(websocket)
    log.info("ws_connected")

    try:
        while True:
            try:
                # ⏳ timeout curto para NÃO bloquear o socket
                msg = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                # ✅ frontend não enviou nada → normal
                continue

            msg_type = msg.get("type")
            data = msg.get("data") or {}

            if msg_type == "player_audio_frame":
                await executor.on_player_audio_frame(
                    step_index=data.get("stepIndex"),
                    elapsed_ms=data.get("elapsedMs"),
                    energy=data.get("energy"),
                    bands=data.get("bands") or {},
                    beat=bool(data.get("beat")),
                )

    except Exception:
        log.info("ws_connection_closed")

    finally:
        await ws_manager.disconnect(websocket)
        log.info("ws_disconnected")