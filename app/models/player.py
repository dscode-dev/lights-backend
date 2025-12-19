from __future__ import annotations

from pydantic import BaseModel
from typing import Literal

Palette = Literal["blue", "purple", "green", "orange"]
StepType = Literal["music", "presentation", "pause"]


class PlayerStatus(BaseModel):
    isPlaying: bool
    activeIndex: int
    elapsedMs: int
    bpm: int
    palette: Palette
    currentTitle: str
    currentType: StepType
