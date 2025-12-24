from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_player_executor
from app.services.playlist_executor import PlaylistExecutor

log = logging.getLogger("api.player")

router = APIRouter(prefix="/player", tags=["player"])


@router.post("/play/{index}")
async def play(index: int, executor: PlaylistExecutor = Depends(get_player_executor)):
    try:
        await executor.play_index(index)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/pause")
async def pause(executor: PlaylistExecutor = Depends(get_player_executor)):
    await executor.pause()
    return {"ok": True}


@router.post("/resume")
async def resume(executor: PlaylistExecutor = Depends(get_player_executor)):
    await executor.resume()
    return {"ok": True}


@router.post("/stop")
async def stop(executor: PlaylistExecutor = Depends(get_player_executor)):
    await executor.stop_playback()
    return {"ok": True}