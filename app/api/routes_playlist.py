from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException

from app.api.deps import get_player_executor, get_state, get_pipeline
from app.models.playlist import PlaylistStep, PlaylistResponse
from app.services.playlist_executor import PlaylistExecutor
from app.services.youtube_pipeline import YouTubePipeline, AddFromYouTubeJob
from app.state.playlist_state import get_playlist, save_playlist
from app.state.redis_keys import EVENTS_CHANNEL
from app.state.redis_state import RedisState

log = logging.getLogger("api.playlist")

router = APIRouter(prefix="/playlist", tags=["playlist"])


# ==========================================================
# LIST PLAYLIST
# ==========================================================
@router.get("", response_model=PlaylistResponse)
async def list_playlist(
    state: RedisState = Depends(get_state),
):
    steps = await get_playlist(state)
    return {"steps": steps}


# ==========================================================
# ADD FROM YOUTUBE (SEM AUDIO)
# ==========================================================
@router.post("/add-from-youtube")
async def add_from_youtube(
    # 🔹 campos vindos do frontend
    title: str = Form(...),
    youtubeUrl: str = Form(...),
    type: Literal["music", "presentation", "pause"] = Form("music"),
    palette: Literal["blue", "purple", "green", "orange"] = Form("blue"),
    genre: str = Form(""),
    useAI: bool = Form(True),

    # 🔹 deps
    state: RedisState = Depends(get_state),
    pipeline: YouTubePipeline = Depends(get_pipeline),
):
    """
    Cria um step em `processing` e despacha o pipeline.
    O pipeline é responsável por:
      - baixar áudio do YouTube
      - analisar áudio
      - gerar plano de LEDs (IA opcional)
    """

    steps = await get_playlist(state)

    step_id = str(uuid.uuid4())

    # cria step inicial (SEM audioFile)
    step = PlaylistStep(
        id=step_id,
        title=title,
        type=type,
        palette=palette,
        genre=genre,
        youtubeUrl=youtubeUrl,
        status="processing",
        progress=0.0,
    )

    steps.append(step)
    await save_playlist(state, steps)

    # publica playlist atualizada
    await state.publish_event(
        EVENTS_CHANNEL,
        {
            "type": "playlist",
            "data": {"steps": [s.model_dump() for s in steps]},
        },
    )

    # evento inicial de progresso
    await state.publish_event(
        EVENTS_CHANNEL,
        {
            "type": "playlist_progress",
            "data": {
                "stepId": step_id,
                "progress": 0.0,
                "stage": "queued",
            },
        },
    )

    # despacha job do pipeline
    job = AddFromYouTubeJob(
        step_id=step_id,
        title=title,
        genre=genre,
        palette=palette,
        youtube_url=youtubeUrl,
        use_ai=useAI,
    )

    await pipeline.dispatch(job)

    log.info(
        "step_created_processing",
        extra={"stepId": step_id, "youtubeUrl": youtubeUrl},
    )

    return {"stepId": step_id}


# ==========================================================
# DELETE STEP
# ==========================================================
@router.delete("/delete/{index}")
async def delete_step(
    index: int,
    state: RedisState = Depends(get_state),
):
    steps = await get_playlist(state)

    if index < 0 or index >= len(steps):
        raise HTTPException(status_code=404, detail="Invalid index")

    removed = steps.pop(index)
    await save_playlist(state, steps)

    await state.publish_event(
        EVENTS_CHANNEL,
        {
            "type": "playlist",
            "data": {"steps": [s.model_dump() for s in steps]},
        },
    )

    log.info("step_deleted", extra={"stepId": removed.id})

    return {"ok": True}

@router.post("/player/pause")
async def pause(
    executor: PlaylistExecutor = Depends(get_player_executor),
    state: RedisState = Depends(get_state),
):
    await executor.pause()
    return {"ok": True}