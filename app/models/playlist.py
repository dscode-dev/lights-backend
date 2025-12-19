from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal, Any, List, Dict


StepType = Literal["music", "presentation", "pause"]
StepStatus = Literal["processing", "ready", "error"]
Palette = Literal["blue", "purple", "green", "orange"]

EspTarget = Literal["right", "left", "portal", "hologram", "broadcast"]
EspCmdType = Literal[
    "set_mode",
    "beat",
    "set_palette",
    "hologram_behavior",
    "portal_mode",
    "pause",
]


class EspCommand(BaseModel):
    target: EspTarget
    type: EspCmdType
    payload: Dict[str, Any] = Field(default_factory=dict)


class PlaylistStep(BaseModel):
    id: str
    title: str
    type: StepType

    status: StepStatus = "processing"
    progress: float = 0.0

    palette: Palette = "blue"
    genre: str = ""

    durationMs: int = 0
    bpm: int = 120

    trackTitle: str = ""
    audioFile: str = ""

    hologram: str = ""
    leds: str = ""
    portal: str = ""

    esp: List[EspCommand] = Field(default_factory=list)


class PlaylistResponse(BaseModel):
    steps: List[PlaylistStep]
