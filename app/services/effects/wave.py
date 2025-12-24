from __future__ import annotations
from app.services.effects.base import BaseEffect, EffectContext, EffectOutput
from app.services.effects.utils import palette_to_hue


class WaveEffect(BaseEffect):
    def apply(self, ctx: EffectContext) -> EffectOutput:
        out = EffectOutput()

        step = (ctx.elapsed_ms // 120) % 360
        hue = (palette_to_hue(ctx.palette) + step) % 360

        out.contour_hue = hue
        return out