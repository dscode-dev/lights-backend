from __future__ import annotations

from app.services.effects.base import BaseEffect, EffectContext
from app.services.effects.output import SegmentOutput


class VuEffect(BaseEffect):
    def apply(self, ctx: EffectContext) -> SegmentOutput:
        out = SegmentOutput()

        energy = ctx.beat.energy_at(ctx.elapsed_ms)

        out.vu_left = int(energy * 31)
        out.vu_right = int(energy * 50)

        return out