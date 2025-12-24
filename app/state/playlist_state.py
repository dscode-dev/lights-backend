from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.state.redis_state import RedisState
from app.state.redis_keys import PLAYLIST_STEPS_KEY


async def get_playlist_raw(state: RedisState) -> List[Dict[str, Any]]:
    data = await state.get_json(PLAYLIST_STEPS_KEY)
    if not data:
        return []
    if isinstance(data, list):
        return data
    return []


async def set_playlist_raw(state: RedisState, steps: List[Dict[str, Any]]) -> None:
    await state.set_json(PLAYLIST_STEPS_KEY, steps)


async def get_step_by_id(
    state: RedisState,
    step_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Retorna um step pelo id ou None se não existir
    """
    steps = await get_playlist_raw(state)
    for step in steps:
        if step.get("id") == step_id:
            return step
    return None


async def upsert_step_by_id(
    state: RedisState,
    step_id: str,
    patch: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Atualiza (merge) um step existente por id.
    Retorna o step atualizado ou None se não achar.
    """
    steps = await get_playlist_raw(state)
    updated: Optional[Dict[str, Any]] = None

    for i, s in enumerate(steps):
        if s.get("id") == step_id:
            new_s = dict(s)
            new_s.update(patch)
            steps[i] = new_s
            updated = new_s
            break

    if updated is None:
        return None

    await set_playlist_raw(state, steps)
    return updated