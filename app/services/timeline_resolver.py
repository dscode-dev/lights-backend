from __future__ import annotations
from typing import Optional, Tuple
from app.models.playlist import PlaylistStep
from app.models.effects import EffectsPreset
from app.services.effects.interpolator import lerp_effect


class TimelineResolver:
    TRANSITION_MS = 2000  # 2 segundos

    def resolve(
        self,
        step: PlaylistStep,
        elapsed_ms: int
    ) -> Optional[EffectsPreset]:
        if not step.effectsTimeline or not step.presets:
            return None

        entries = sorted(step.effectsTimeline.timeline, key=lambda x: x.atMs)

        prev_entry = None
        next_entry = None

        for e in entries:
            if elapsed_ms >= e.atMs:
                prev_entry = e
            else:
                next_entry = e
                break

        if not prev_entry:
            return None

        current = step.presets.get(prev_entry.presetName)
        if not next_entry:
            return current

        delta = elapsed_ms - prev_entry.atMs
        if delta > self.TRANSITION_MS:
            return current

        t = min(delta / self.TRANSITION_MS, 1.0)
        next_preset = step.presets.get(next_entry.presetName)

        return EffectsPreset(
            vu=lerp_effect(current.vu, next_preset.vu, t),
            contour=lerp_effect(current.contour, next_preset.contour, t),
            portal=lerp_effect(current.portal, next_preset.portal, t),
            hologram=lerp_effect(current.hologram, next_preset.hologram, t),
        )