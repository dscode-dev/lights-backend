from fastapi import APIRouter, Depends
from app.services.playlist_executor import PlaylistExecutor
from app.api.deps import get_player_executor

router = APIRouter(prefix="/player", tags=["player"])


@router.post("/play/{index}")
async def play(index: int, executor: PlaylistExecutor = Depends(get_player_executor)):
    await executor.play_index(index)
    return {"ok": True}


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
    await executor.stop()
    return {"ok": True}