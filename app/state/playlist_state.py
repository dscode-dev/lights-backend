from __future__ import annotations

from typing import List
from app.models.playlist import PlaylistStep
from app.state.redis_state import RedisState
from app.state.redis_keys import PLAYLIST_STEPS_KEY


async def get_playlist(state: RedisState) -> List[PlaylistStep]:
    raw = await state.get_json(PLAYLIST_STEPS_KEY)
    if not raw:
        return []
    return [PlaylistStep.model_validate(s) for s in raw]


async def save_playlist(state: RedisState, steps: List[PlaylistStep]) -> None:
    await state.set_json(
        PLAYLIST_STEPS_KEY,
        [s.model_dump() for s in steps],
    )
