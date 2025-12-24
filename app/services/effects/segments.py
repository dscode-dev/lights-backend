from __future__ import annotations
from enum import Enum


class Segment(str, Enum):
    VU = "vu"
    CONTOUR = "contour"
    PORTAL = "portal"
    HOLOGRAM = "hologram"