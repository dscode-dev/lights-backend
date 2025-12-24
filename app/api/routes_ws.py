from fastapi import APIRouter, WebSocket, Depends

from app.api.deps import (
    get_player_executor_ws,
    get_ws_manager_ws,
)
from app.services.playlist_executor import PlaylistExecutor
from app.ws.manager import WebSocketManager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    executor: PlaylistExecutor = Depends(get_player_executor_ws),
    ws_manager: WebSocketManager = Depends(get_ws_manager_ws),
):
    await ws_manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        await ws_manager.disconnect(websocket)