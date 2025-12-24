# app/models/playlist.py
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


StepStatus = Literal["processing", "ready", "error"]
StepType = Literal["music", "presentation", "pause"]


class EspCommand(BaseModel):
    atMs: Optional[int] = None
    target: Literal["right", "left", "portal", "hologram", "broadcast"]
    type: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class PlaylistStep(BaseModel):
    # ids
    id: str
    title: str

    # core
    type: StepType = "music"
    status: StepStatus = "processing"
    progress: float = 0.0

    # visual/audio meta
    palette: Literal["blue", "purple", "green", "orange"] = "blue"
    genre: str = ""

    # IMPORTANT: durante processing esses campos podem não existir ainda.
    # Então damos defaults seguros para não quebrar GET /playlist.
    durationMs: int = 0
    bpm: int = 0

    trackTitle: str = ""
    audioFile: str = ""  # não pode ser None; se não tiver ainda, fica ""

    hologram: str = ""
    leds: str = ""
    portal: str = ""

    youtubeUrl: str = ""

    esp: List[EspCommand] = Field(default_factory=list)

    # opcional para UI
    pipelineStage: Optional[str] = None


class PlaylistResponse(BaseModel):
    steps: List[PlaylistStep]