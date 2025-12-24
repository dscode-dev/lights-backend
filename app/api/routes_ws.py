from __future__ import annotations

import json
import logging
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from app.api.deps import get_ws_manager_ws, get_player_executor_ws
from app.ws.manager import WebSocketManager
from app.services.playlist_executor import PlaylistExecutor

log = logging.getLogger("api.ws")

router = APIRouter(tags=["ws"])


def _safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        return None


@router.websocket("/ws")
async def ws_endpoint(
    websocket: WebSocket,
    ws: WebSocketManager = Depends(get_ws_manager_ws),
    executor: PlaylistExecutor = Depends(get_player_executor_ws),
):
    """
    WS único:
    - Backend -> Frontend: eventos (status, playlist, progress)
    - Frontend -> Backend: player_frame (clock master)
    """
    await ws.connect(websocket)
    log.info("ws_connected")

    try:
        while True:
            msg = await websocket.receive_text()
            payload = _safe_json_loads(msg)
            if not payload:
                continue

            msg_type = payload.get("type")
            data = payload.get("data") or {}

            if msg_type == "player_frame":
                # contrato
                step_id = str(data.get("stepId") or "")
                player_time = float(data.get("playerTime") or 0.0)
                duration = float(data.get("duration") or 0.0)
                state = str(data.get("state") or "playing")

                if not step_id:
                    continue

                if state not in ("playing", "paused", "ended", "idle"):
                    state = "playing"

                await executor.sync_frame(
                    step_id=step_id,
                    player_time_s=player_time,
                    duration_s=duration,
                    state=state,  # type: ignore[arg-type]
                )
            else:
                # Ignora outros tipos por enquanto (mantém robusto)
                continue

    except WebSocketDisconnect:
        log.info("ws_disconnected")
    except Exception:
        log.exception("ws_error")
    finally:
        await ws.disconnect(websocket)