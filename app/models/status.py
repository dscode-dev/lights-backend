from __future__ import annotations

from pydantic import BaseModel
from typing import Literal, Optional


class PlayerStatus(BaseModel):
    isPlaying: bool = False
    activeIndex: int = 0
    elapsedMs: int = 0
    bpm: int = 128
    palette: str = "blue"
    currentTitle: str = ""
    currentType: Literal["music", "presentation", "pause"] = "music"
    currentStepId: Optional[str] = None