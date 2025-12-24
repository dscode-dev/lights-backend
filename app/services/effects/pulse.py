from __future__ import annotations

from app.services.effects.base import BaseEffect, EffectContext
from app.services.effects.output import SegmentOutput
from app.services.effects.utils import palette_to_hue


class PulseEffect(BaseEffect):
    def apply(self, ctx: EffectContext) -> SegmentOutput:
        out = SegmentOutput()

        energy = ctx.beat.energy_at(ctx.elapsed_ms)

        if energy < 0.15:
            out.contour_off = True
        else:
            out.contour_hue = palette_to_hue(ctx.palette)

        return out