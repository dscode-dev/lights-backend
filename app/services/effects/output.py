from __future__ import annotations
from typing import Dict


class SegmentOutput:
    def __init__(self):
        self.vu_left: int | None = None
        self.vu_right: int | None = None
        self.contour_hue: int | None = None
        self.contour_off: bool = False