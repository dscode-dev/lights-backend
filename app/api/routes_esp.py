from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_state
from app.state.redis_state import RedisState
from app.state.redis_keys import ESP_NODES_KEY, EVENTS_CHANNEL

router = APIRouter(prefix="/esp", tags=["esp"])


@router.get("/status")
async def esp_status(state: RedisState = Depends(get_state)):
    nodes = await state.get_json(ESP_NODES_KEY)
    if nodes is None:
        nodes = []
        await state.set_json(ESP_NODES_KEY, nodes)
    return {"nodes": nodes}


@router.post("/refresh")
async def esp_refresh(state: RedisState = Depends(get_state)):
    # firmware UDP não “responde”, então refresh aqui é só “republicar estado”
    nodes = await state.get_json(ESP_NODES_KEY)
    if nodes is None:
        nodes = []
        await state.set_json(ESP_NODES_KEY, nodes)

    await state.publish_event(EVENTS_CHANNEL, {"type": "esp", "data": {"nodes": nodes}})
    return {"ok": True, "nodes": nodes}