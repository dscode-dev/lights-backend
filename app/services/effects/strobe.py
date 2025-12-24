from __future__ import annotations
from app.services.effects.base import BaseEffect, EffectContext, EffectOutput
from app.services.effects.utils import palette_to_hue


class StrobeEffect(BaseEffect):
    def apply(self, ctx: EffectContext) -> EffectOutput:
        out = EffectOutput()

        if (ctx.elapsed_ms // 100) % 2 == 0:
            out.contour_hue = palette_to_hue(ctx.palette)
        else:
            out.contour_off = True

        return out