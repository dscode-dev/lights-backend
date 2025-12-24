from __future__ import annotations

from app.services.effects.vu import VuEffect
from app.services.effects.pulse import PulseEffect
from app.services.effects.output import SegmentOutput
from app.services.effects.base import EffectContext
from app.services.effects.segments import Segment


class EffectEngine:
    def __init__(self):
        self.registry = {
            "vu": VuEffect(),
            "pulse": PulseEffect(),
        }

    def apply(self, ctx: EffectContext, preset) -> dict[Segment, SegmentOutput]:
        outputs: dict[Segment, SegmentOutput] = {}

        if preset is None:
            return outputs

        if preset.vu:
            fx = self.registry.get(preset.vu.effect)
            if fx:
                outputs[Segment.VU] = fx.apply(ctx)

        if preset.contour:
            fx = self.registry.get(preset.contour.effect)
            if fx:
                outputs[Segment.CONTOUR] = fx.apply(ctx)

        return outputs