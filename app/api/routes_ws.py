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
    executor=Depends(get_player_executor_ws),
    ws_manager=Depends(get_ws_manager_ws),
):
    # aceita conexão (importante: manager já cuida do accept)
    await ws_manager.connect(websocket)
    log.info("ws_connected")

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")
            data = msg.get("data") or {}

            # =========================
            # 🎯 CLOCK VINDO DO FRONTEND
            # =========================
            if msg_type == "player_tick":
                # contrato já existente (NÃO MUDOU)
                await executor.on_player_tick(
                    step_index=data.get("stepIndex"),
                    elapsed_ms=data.get("elapsedMs"),
                )
                continue

            # ==========================================
            # 🔊 AUDIO FRAME (ENERGIA REAL DO SOM)
            # ==========================================
            if msg_type == "player_audio_frame":
                """
                data esperado (exatamente como o frontend já gera):
                {
                  ts: number,
                  energy: number (0..1),
                  bands: { bass: number, mid: number, treble: number },
                  beat: boolean
                }
                """
                await executor.on_audio_frame(
                    energy=data.get("energy", 0.0),
                    bands=data.get("bands") or {},
                    beat=bool(data.get("beat", False)),
                )
                continue

            # =========================
            # Outros tipos (futuro)
            # =========================
            log.debug("ws_unknown_message", extra={"msg": msg})

    except Exception:
        log.exception("ws_connection_closed")
    finally:
        await ws_manager.disconnect(websocket)
        log.info("ws_disconnected")