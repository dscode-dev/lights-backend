from __future__ import annotations

from typing import List

from app.models.playlist import PlaylistStep
from app.state.redis_keys import PLAYLIST_STEPS_KEY
from app.state.redis_state import RedisState


async def get_playlist(state: RedisState) -> List[PlaylistStep]:
    data = await state.get_json(PLAYLIST_STEPS_KEY)
    if not data:
        return []
    return [PlaylistStep(**x) for x in data]


async def save_playlist(state: RedisState, steps: List[PlaylistStep]) -> None:
    await state.set_json(PLAYLIST_STEPS_KEY, [s.model_dump() for s in steps])