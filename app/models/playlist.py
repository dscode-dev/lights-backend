from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


class PlaylistStep(BaseModel):
    id: str
    title: str
    type: str
    palette: str
    genre: Optional[str] = None
    youtubeUrl: Optional[str] = None

    status: str = "processing"  # processing | ready | error
    durationMs: Optional[int] = None
    bpm: Optional[int] = None
    beatMap: Optional[list[int]] = None
    ledPlan: Optional[dict] = None
    error: Optional[str] = None


class PlaylistResponse(BaseModel):
    steps: List[PlaylistStep]