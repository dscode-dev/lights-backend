from __future__ import annotations

import logging
import numpy as np
import librosa

log = logging.getLogger("audio.analyzer")


class AudioAnalyzer:
    def analyze(self, path: str) -> dict:
        log.info("audio_load_start", extra={"path": path})

        # sr=None preserva taxa nativa
        y, sr = librosa.load(path, sr=None, mono=True)

        duration_s = float(librosa.get_duration(y=y, sr=sr))
        duration_ms = int(duration_s * 1000)

        log.info("audio_load_ok", extra={"sr": sr, "durationMs": duration_ms})

        # BPM + beats
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
        bpm = int(round(float(tempo))) if tempo and tempo > 0 else 128

        # garantir mínimo 128 (seu requisito)
        if bpm < 128:
            bpm = 128

        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        beat_ms = [int(t * 1000) for t in beat_times.tolist()]

        # Normaliza beatmap se vier vazio
        if not beat_ms:
            # fallback: beat regular por BPM
            interval = int(60000 / bpm)
            beat_ms = list(range(0, duration_ms, interval))[:1000]

        log.info("audio_analysis_ok", extra={"bpm": bpm, "beats": len(beat_ms)})

        return {
            "durationMs": duration_ms,
            "bpm": bpm,
            "beatMap": beat_ms,
        }