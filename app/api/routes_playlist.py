# app/api/routes_playlist.py
from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Form, HTTPException

from app.state.playlist_state import (
    get_playlist_raw,
    set_playlist_raw,
)

from app.services.youtube_pipeline import YouTubePipeline

router = APIRouter(prefix="/playlist", tags=["playlist"])


# =====================================================
# LIST PLAYLIST
# =====================================================

@router.get("")
async def list_playlist(request: Request):
    state = request.app.state.state
    steps = await get_playlist_raw(state)
    return {"steps": steps}


# =====================================================
# ADD STEP FROM YOUTUBE (MODAL DO FRONTEND)
# =====================================================

@router.post("/add-from-youtube")
async def add_from_youtube(
    request: Request,
    title: str = Form(...),
    youtubeUrl: str = Form(...),
    genre: str = Form(""),
    palette: str = Form("blue"),
    useAi: bool = Form(False),  # mantido só por compatibilidade
):
    state = request.app.state.state
    pipeline: YouTubePipeline = request.app.state.pipeline

    steps = await get_playlist_raw(state)

    step_id = str(uuid.uuid4())

    step = {
        "id": step_id,
        "title": title,
        "type": "music",

        "status": "processing",
        "progress": 0.0,

        "genre": genre,
        "palette": palette,

        "durationMs": 0,
        "bpm": 0,
        "trackTitle": "",
        "audioFile": "",
        "youtubeUrl": youtubeUrl,

        "hologram": "",
        "leds": "",
        "portal": "",

        "esp": [],
    }

    steps.append(step)
    await set_playlist_raw(state, steps)

    # ✅ CHAMADA CORRETA DO PIPELINE
    await pipeline.enqueue(
        step_id=step_id,
        title=title,
        youtube_url=youtubeUrl,
    )

    return {"ok": True, "step": step}


# =====================================================
# DELETE STEP
# =====================================================

@router.delete("/delete/{index}")
async def delete_step(index: int, request: Request):
    state = request.app.state.state
    steps = await get_playlist_raw(state)

    if index < 0 or index >= len(steps):
        raise HTTPException(status_code=404, detail="Step não encontrado")

    steps.pop(index)
    await set_playlist_raw(state, steps)

    return {"ok": True}