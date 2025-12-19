from __future__ import annotations

from pydantic import BaseModel
from typing import Literal, List

EspNodeId = Literal["right", "left", "portal", "hologram"]
EspOnlineStatus = Literal["online", "offline"]


class EspNode(BaseModel):
    id: EspNodeId
    name: str
    status: EspOnlineStatus
    lastPing: str
    routes: List[str]


class EspStatusResponse(BaseModel):
    nodes: List[EspNode]
