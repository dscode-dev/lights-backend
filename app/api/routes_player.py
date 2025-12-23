from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_state, get_player_executor
from app.state.redis_state import RedisState
from app.state.playlist_state import get_playlist
from app.services.playlist_executor import PlaylistExecutor

router = APIRouter(tags=["player"])


class PlayStepRequest(BaseModel):
    index: int


@router.post("/play-step")
async def play_step(
    payload: PlayStepRequest,
    state: RedisState = Depends(get_state),
    executor: PlaylistExecutor = Depends(get_player_executor),
):
    steps = await get_playlist(state)

    if payload.index < 0 or payload.index >= len(steps):
        raise HTTPException(status_code=404, detail="Invalid index")

    step = steps[payload.index]
    if step.status == "processing":
        raise HTTPException(status_code=409, detail="Step is processing")
    if step.status == "error":
        raise HTTPException(status_code=409, detail="Step errored")

    await executor.play_index(payload.index)
    return {"ok": True}


@router.post("/stop")
async def stop(
    executor: PlaylistExecutor = Depends(get_player_executor),
):
    await executor.stop_playback()
    return {"ok": True}