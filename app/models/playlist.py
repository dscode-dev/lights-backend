from __future__ import annotations

from typing import Literal, Optional, List, Dict
from pydantic import BaseModel, Field


class PlaylistStep(BaseModel):
    id: str
    title: str

    type: Literal["music", "presentation", "pause"] = "music"
    palette: Literal["blue", "purple", "green", "orange"] = "blue"
    genre: str = ""

    youtubeUrl: Optional[str] = None

    # =========================
    # STATUS / PIPELINE
    # =========================
    status: Literal["idle", "processing", "ready", "error"] = "idle"

    progress: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Pipeline progress from 0.0 to 1.0",
    )

    error: Optional[str] = None

    # =========================
    # AUDIO / ANALYSIS
    # =========================
    durationMs: Optional[int] = None
    bpm: Optional[int] = None
    beatMap: Optional[List[int]] = None

    # =========================
    # LED PLAN
    # =========================
    ledPlan: Optional[Dict] = None

    # =========================
    # AUDIO FILE (BACKEND GENERATED)
    # =========================
    audioFile: Optional[str] = None

class PlaylistResponse(BaseModel):
    steps: List[PlaylistStep]
# =========================
# PAYLOADS DE API
# =========================

class AddFromYouTubePayload(BaseModel):
    """
    Payload recebido do frontend.
    IMPORTANTE: durationMs NÃO vem daqui.
    """
    title: str
    type: PlaylistType
    palette: str
    genre: Optional[str] = None
    youtubeUrl: str
    useAI: bool = False

    class Config:
        extra = "forbid"