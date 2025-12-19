from __future__ import annotations

from fastapi import APIRouter, Depends
from app.api.deps import get_state
from app.state.player_state import get_player_status
from app.state.redis_state import RedisState

router = APIRouter(tags=["status"])


@router.get("/status")
async def status(state: RedisState = Depends(get_state)):
    return await get_player_status(state)
