from __future__ import annotations

import datetime
from fastapi import APIRouter, Depends

from app.api.deps import get_state
from app.core.config import settings
from app.models.esp import EspNode
from app.services.esp_client import ping_esp, blink_esp
from app.state.redis_keys import ESP_NODES_KEY, EVENTS_CHANNEL
from app.state.redis_state import RedisState

router = APIRouter(prefix="/esp", tags=["esp"])


@router.get("/status")
async def esp_status(state: RedisState = Depends(get_state)):
    raw = await state.get_json(ESP_NODES_KEY)
    return {"nodes": raw or []}


@router.post("/refresh")
async def refresh_esp(state: RedisState = Depends(get_state)):
    nodes: list[EspNode] = []

    for esp_id, ip in settings.esp_registry.items():
        online = await ping_esp(ip)
        if online:
            await blink_esp(ip)

        node = EspNode(
            id=esp_id,  # type: ignore[arg-type]
            name=f"ESP {esp_id.capitalize()}",
            status="online" if online else "offline",
            lastPing=datetime.datetime.utcnow().isoformat(),
            routes=["VU", "Contorno", "Portal"],
        )
        nodes.append(node)

    await state.set_json(
        ESP_NODES_KEY,
        [n.model_dump() for n in nodes],
    )

    await state.publish_event(
        EVENTS_CHANNEL,
        {"type": "esp", "data": {"nodes": [n.model_dump() for n in nodes]}},
    )

    return {"nodes": nodes}
