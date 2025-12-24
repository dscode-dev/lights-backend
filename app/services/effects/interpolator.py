from __future__ import annotations
from typing import Optional
from app.models.effects import EffectConfig


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_effect(
    a: Optional[EffectConfig],
    b: Optional[EffectConfig],
    t: float
) -> Optional[EffectConfig]:
    if a is None:
        return b
    if b is None:
        return a
    if a.effect != b.effect:
        return b 

    params = {}
    for k in set(a.params.keys()) | set(b.params.keys()):
        va = a.params.get(k)
        vb = b.params.get(k)

        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            params[k] = lerp(float(va), float(vb), t)
        else:
            params[k] = vb if t > 0.5 else va

    return EffectConfig(effect=a.effect, params=params)