from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_state
from app.state.redis_state import RedisState
from app.state.playlist_state import get_playlist
from app.state.player_state import get_player_status, save_player_status
from app.state.redis_keys import EVENTS_CHANNEL

log = logging.getLogger("api.player")

router = APIRouter(tags=["player"])


@router.post("/play")
async def play(state: RedisState = Depends(get_state)):
    steps = await get_playlist(state)
    status = await get_player_status(state)

    if not steps:
        raise HTTPException(status_code=400, detail="Playlist is empty")

    # ensure active step is ready
    if status.activeIndex < 0:
        status.activeIndex = 0
    if status.activeIndex >= len(steps):
        status.activeIndex = len(steps) - 1

    if steps[status.activeIndex].status != "ready":
        raise HTTPException(status_code=400, detail="Active step is not ready")

    status.isPlaying = True
    await save_player_status(state, status)
    await state.publish_event(EVENTS_CHANNEL, {"type": "status", "data": status.model_dump()})
    return {"ok": True}


@router.post("/pause")
async def pause(state: RedisState = Depends(get_state)):
    status = await get_player_status(state)
    status.isPlaying = False
    await save_player_status(state, status)
    await state.publish_event(EVENTS_CHANNEL, {"type": "status", "data": status.model_dump()})
    return {"ok": True}


@router.post("/skip")
async def skip(state: RedisState = Depends(get_state)):
    steps = await get_playlist(state)
    status = await get_player_status(state)

    if not steps:
        raise HTTPException(status_code=400, detail="Playlist is empty")

    idx = status.activeIndex + 1
    if idx >= len(steps):
        idx = len(steps) - 1

    # find next ready
    found = None
    for j in range(idx, len(steps)):
        if steps[j].status == "ready":
            found = j
            break
    if found is None:
        # no ready steps ahead; stop
        status.isPlaying = False
        await save_player_status(state, status)
        await state.publish_event(EVENTS_CHANNEL, {"type": "status", "data": status.model_dump()})
        return {"ok": True, "stopped": True}

    status.activeIndex = found
    status.elapsedMs = 0
    status.isPlaying = True
    await save_player_status(state, status)
    await state.publish_event(EVENTS_CHANNEL, {"type": "status", "data": status.model_dump()})
    return {"ok": True, "activeIndex": found}


@router.post("/play-step")
async def play_step(payload: dict, state: RedisState = Depends(get_state)):
    """
    payload:
      { "index": 3 }
    """
    steps = await get_playlist(state)
    status = await get_player_status(state)

    if not steps:
        raise HTTPException(status_code=400, detail="Playlist is empty")

    index = payload.get("index")
    if index is None:
        raise HTTPException(status_code=400, detail="Missing index")
    if not isinstance(index, int):
        raise HTTPException(status_code=400, detail="Index must be int")
    if index < 0 or index >= len(steps):
        raise HTTPException(status_code=404, detail="Invalid index")

    if steps[index].status != "ready":
        raise HTTPException(status_code=400, detail="Step is not ready")

    status.activeIndex = index
    status.elapsedMs = 0
    status.isPlaying = True
    await save_player_status(state, status)
    await state.publish_event(EVENTS_CHANNEL, {"type": "status", "data": status.model_dump()})
    return {"ok": True}
