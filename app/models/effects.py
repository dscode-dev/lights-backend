from __future__ import annotations
from typing import Optional, Dict
from pydantic import BaseModel


class EffectConfig(BaseModel):
    effect: str
    params: Dict[str, float | int | str | bool] = {}


class EffectsPreset(BaseModel):
    vu: Optional[EffectConfig] = None
    contour: Optional[EffectConfig] = None
    portal: Optional[EffectConfig] = None
    hologram: Optional[EffectConfig] = None