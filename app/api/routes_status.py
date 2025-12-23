from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_state
from app.state.redis_state import RedisState
from app.state.redis_keys import PLAYER_STATUS_KEY
from app.models.status import PlayerStatus

router = APIRouter(prefix="/status", tags=["status"])


@router.get("")
async def get_status(state: RedisState = Depends(get_state)):
    raw = await state.get_json(PLAYER_STATUS_KEY)
    if not raw:
        status = PlayerStatus().model_dump()
        await state.set_json(PLAYER_STATUS_KEY, status)
        return status
    return raw