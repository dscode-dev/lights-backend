from __future__ import annotations

import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
import json
import os
from pydantic import BaseModel
from typing import Literal

from app.api.deps import get_state
from app.models.playlist import PlaylistStep, PlaylistResponse
from app.state.playlist_state import get_playlist, save_playlist
from app.state.redis_keys import EVENTS_CHANNEL
from app.state.redis_state import RedisState
from app.workers.background import run_coro
from app.services.youtube_pipeline import YouTubePipeline, AddFromYouTubeJob
from app.services.presentation_pipeline import PresentationPipeline

log = logging.getLogger("api.playlist")

router = APIRouter(prefix="/playlist", tags=["playlist"])


class AddFromYouTubeRequest(BaseModel):
    title: str
    type: Literal["music", "presentation", "pause"] = "music"
    palette: Literal["blue", "purple", "green", "orange"] = "blue"
    genre: str = ""
    youtubeUrl: str
    useAI: bool = True


@router.get("", response_model=PlaylistResponse)
async def list_playlist(state: RedisState = Depends(get_state)):
    steps = await get_playlist(state)
    return {"steps": steps}


@router.post("/add-from-youtube")
async def add_from_youtube(
    req: AddFromYouTubeRequest,
    background: BackgroundTasks,
    state: RedisState = Depends(get_state),
):
    """
    Non-blocking:
      - creates step status=processing at end
      - returns immediately
      - background pipeline downloads + analyzes + marks ready
    """
    steps = await get_playlist(state)

    step_id = str(uuid.uuid4())

    step = PlaylistStep(
        id=step_id,
        title=req.title,
        type=req.type,
        palette=req.palette,
        genre=req.genre,
        status="processing",
        progress=0.0,
    )

    steps.append(step)
    await save_playlist(state, steps)

    # evento inicial de progress
    await state.publish_event(
        EVENTS_CHANNEL,
        {"type": "playlist_progress", "data": {"stepId": step_id, "progress": 0.0}},
    )

    # start pipeline in background
    pipeline = YouTubePipeline(state)
    job = AddFromYouTubeJob(step_id=step_id, youtube_url=req.youtubeUrl, use_ai=req.useAI)

    run_coro(background, pipeline.run(job))

    log.info("step_created_processing", extra={"stepId": step_id})
    return {"stepId": step_id}


@router.put("/edit/{index}")
async def edit_step(
    index: int,
    payload: dict,
    state: RedisState = Depends(get_state),
):
    steps = await get_playlist(state)

    if index < 0 or index >= len(steps):
        raise HTTPException(status_code=404, detail="Invalid index")

    step = steps[index]
    if step.status == "processing":
        raise HTTPException(status_code=400, detail="Step is processing")

    for k, v in payload.items():
        if hasattr(step, k):
            setattr(step, k, v)

    steps[index] = step
    await save_playlist(state, steps)

    return {"ok": True}


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

    log.info("step_deleted", extra={"stepId": removed.id})
    return {"ok": True}

@router.post("/add-presentation")
async def add_presentation(
    title: str = Form(...),
    palette: str = Form("blue"),
    genre: str = Form(""),
    audio: UploadFile = File(...),
    sequence: UploadFile = File(...),
    background: BackgroundTasks = BackgroundTasks(),
    state: RedisState = Depends(get_state),
):
    steps = await get_playlist(state)
    step_id = str(uuid.uuid4())

    # salvar arquivos
    audio_path = os.path.join(settings.media_dir, f"{step_id}_presentation.mp3")
    seq_path = os.path.join(settings.media_dir, f"{step_id}_sequence.json")

    with open(audio_path, "wb") as f:
        f.write(await audio.read())

    with open(seq_path, "wb") as f:
        f.write(await sequence.read())

    with open(seq_path, "r", encoding="utf-8") as f:
        seq_json = json.load(f)

    step = PlaylistStep(
        id=step_id,
        title=title,
        type="presentation",
        palette=palette,
        genre=genre,
        status="processing",
        progress=0.0,
    )

    steps.append(step)
    await save_playlist(state, steps)

    pipeline = PresentationPipeline(state)

    run_coro(
        background,
        pipeline.run(
            step_id=step_id,
            title=title,
            palette=palette,
            genre=genre,
            audio_path=audio_path,
            sequence=seq_json,
        ),
    )

    return {"stepId": step_id}
