from __future__ import annotations

import logging
from dataclasses import dataclass

import librosa
import numpy as np

log = logging.getLogger("audio.analyzer")


@dataclass
class AudioAnalysisResult:
    duration_ms: int
    bpm: int
    beat_map: list[int]
    energy_map: list[dict]


def analyze_audio_file(path: str) -> AudioAnalysisResult:
    log.info("audio_load_start", extra={"path": path})

    y, sr = librosa.load(path, sr=None, mono=True)

    duration_s = librosa.get_duration(y=y, sr=sr)
    duration_ms = int(duration_s * 1000)

    # ==========================
    # BPM + BEATS
    # ==========================
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beats, sr=sr)
    beat_map = [int(t * 1000) for t in beat_times]

    # ==========================
    # ENERGY (RMS)
    # ==========================
    hop_length = 512
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    times = librosa.frames_to_time(
        np.arange(len(rms)),
        sr=sr,
        hop_length=hop_length,
    )

    rms_max = float(np.max(rms)) or 1.0

    energy_map = [
        {
            "t": int(t * 1000),
            "e": float(v / rms_max),
        }
        for t, v in zip(times, rms)
    ]

    log.info(
        "audio_analysis_ok",
        extra={
            "duration_ms": duration_ms,
            "bpm": int(round(tempo)),
            "beats": len(beat_map),
            "energy_points": len(energy_map),
        },
    )

    return AudioAnalysisResult(
        duration_ms=duration_ms,
        bpm=int(round(tempo)),
        beat_map=beat_map,
        energy_map=energy_map,
    )