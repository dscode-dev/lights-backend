from fastapi import APIRouter, WebSocket, Depends
import logging
import time

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
    log.info("ws_connected_frontend")

    last_log_ts = 0.0

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")
            data = msg.get("data") or {}

            # =========================
            # 🎯 AUDIO FRAME DO FRONTEND
            # =========================
            if msg_type == "player_audio_frame":
                now = time.monotonic()

                # 🔕 throttle de log (1x a cada 500ms)
                if now - last_log_ts > 0.5:
                    last_log_ts = now
                    log.info(
                        "audio_frame_rx",
                        extra={
                            "stepIndex": data.get("stepIndex"),
                            "elapsedMs": data.get("elapsedMs"),
                            "energy": data.get("energy"),
                            "beat": data.get("beat"),
                        },
                    )

                await executor.on_player_audio_frame(
                    step_index=data.get("stepIndex"),
                    elapsed_ms=data.get("elapsedMs"),
                    energy=data.get("energy"),
                    bands=data.get("bands") or {},
                    beat=bool(data.get("beat")),
                )
                continue

            log.debug("ws_unknown_msg", extra={"msg": msg})

    except Exception as e:
        log.warning("ws_connection_closed", extra={"error": str(e)})
    finally:
        await ws_manager.disconnect(websocket)
        log.info("ws_disconnected_frontend")