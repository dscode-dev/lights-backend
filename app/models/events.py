from __future__ import annotations

from pydantic import BaseModel
from typing import Literal, Any, Dict
from app.models.playlist import PlaylistStep
from app.models.player import PlayerStatus
from app.models.esp import EspNode


EventType = Literal[
    "playlist_progress",
    "playlist_ready",
    "playlist_error",
    "status",
    "esp",
]


class WsEvent(BaseModel):
    type: EventType
    data: Dict[str, Any]


class PlaylistProgressData(BaseModel):
    stepId: str
    progress: float


class PlaylistReadyData(BaseModel):
    step: PlaylistStep


class PlaylistErrorData(BaseModel):
    stepId: str
    error: str


class StatusData(BaseModel):
    __root__: PlayerStatus


class EspData(BaseModel):
    nodes: list[EspNode]
