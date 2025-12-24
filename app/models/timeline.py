from __future__ import annotations
from typing import List
from pydantic import BaseModel


class TimelineEntry(BaseModel):
    atMs: int
    presetName: str


class EffectsTimeline(BaseModel):
    timeline: List[TimelineEntry]