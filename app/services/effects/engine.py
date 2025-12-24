from __future__ import annotations
from typing import Dict, Optional
from app.models.effects import EffectsPreset
from app.services.effects.base import EffectContext, EffectOutput
from app.services.effects.segments import Segment

from app.services.effects.vu import VUEffect
from app.services.effects.contour import ContourEffect
from app.services.effects.portal import PortalEffect


class EffectEngine:
    def __init__(self):
        self.vu = VUEffect()
        self.contour = ContourEffect()
        self.portal = PortalEffect()

    def apply(
        self,
        ctx: EffectContext,
        preset: Optional[EffectsPreset]
    ) -> Dict[Segment, EffectOutput]:

        outputs: Dict[Segment, EffectOutput] = {}

        if not preset:
            return outputs

        if preset.vu:
            outputs[Segment.VU] = self.vu.apply(ctx, preset.vu)

        if preset.contour:
            outputs[Segment.CONTOUR] = self.contour.apply(ctx, preset.contour)

        if preset.portal:
            outputs[Segment.PORTAL] = self.portal.apply(ctx, preset.portal)

        return outputs