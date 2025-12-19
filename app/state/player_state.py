from __future__ import annotations

from app.models.player import PlayerStatus
from app.state.redis_state import RedisState
from app.state.redis_keys import PLAYER_STATUS_KEY


async def get_player_status(state: RedisState) -> PlayerStatus:
    raw = await state.get_json(PLAYER_STATUS_KEY)
    return PlayerStatus.model_validate(raw)


async def save_player_status(state: RedisState, status: PlayerStatus) -> None:
    await state.set_json(PLAYER_STATUS_KEY, status.model_dump())
