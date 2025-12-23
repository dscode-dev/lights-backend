from fastapi import APIRouter, WebSocket, Depends
from app.api.deps import get_ws_manager_ws
from app.ws.manager import WebSocketManager

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    manager: WebSocketManager = Depends(get_ws_manager_ws),
):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        await manager.disconnect(websocket)