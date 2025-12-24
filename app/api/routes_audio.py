# app/api/routes_audio.py
from __future__ import annotations

import os
import logging
from fastapi import APIRouter, Request, HTTPException
from starlette.responses import FileResponse

from app.state.playlist_state import get_step_by_id

log = logging.getLogger("audio")

router = APIRouter(prefix="/audio", tags=["audio"])


@router.get("/stream/{step_id}")
async def stream_audio(step_id: str, request: Request):
    """
    Stream simples via FileResponse.
    O frontend só precisa apontar o <audio src="..."> pra cá.
    """
    state = request.app.state.state

    step = await get_step_by_id(state, step_id)
    if not step:
        log.warning("audio_stream_step_not_found", extra={"step_id": step_id})
        raise HTTPException(status_code=404, detail="Step não encontrado")

    audio_file = step.get("audioFile") or ""
    if not isinstance(audio_file, str) or not audio_file.strip():
        log.warning("audio_stream_missing_audioFile", extra={"step_id": step_id})
        raise HTTPException(status_code=404, detail="Áudio não disponível (audioFile vazio)")

    audio_path = audio_file

    # aceita relativo (ex: "./media/xxx.wav") e normaliza
    audio_path = os.path.abspath(audio_path)

    if not os.path.exists(audio_path):
        log.warning(
            "audio_stream_file_not_found",
            extra={"step_id": step_id, "audio_path": audio_path},
        )
        raise HTTPException(status_code=404, detail="Arquivo de áudio não encontrado")

    # WAV
    return FileResponse(
        path=audio_path,
        media_type="audio/wav",
        filename=os.path.basename(audio_path),
    )