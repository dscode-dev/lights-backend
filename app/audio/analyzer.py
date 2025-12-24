from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

import librosa
import numpy as np

log = logging.getLogger("audio.analyzer")


@dataclass
class AudioAnalysisResult:
    duration_ms: int
    bpm: int
    beat_map: List[int]
    energy_map: List[float]


def analyze_audio_file(path: str) -> AudioAnalysisResult:
    log.info("audio_load_start", extra={"path": path})

    y, sr = librosa.load(path, sr=None, mono=True)

    duration_s = librosa.get_duration(y=y, sr=sr)
    duration_ms = int(duration_s * 1000)

    # =========================
    # BEATS
    # =========================
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beats, sr=sr)
    beat_map = [int(t * 1000) for t in beat_times]

    # =========================
    # ENERGIA (RMS)
    # =========================
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]

    # normaliza energia (sensível até música baixa)
    rms = rms / (np.max(rms) + 1e-6)
    rms = np.sqrt(rms)  # 🔥 aumenta sensibilidade em volumes baixos

    energy_map = rms.tolist()

    log.info(
        "audio_analysis_ok",
        extra={
            "duration_ms": duration_ms,
            "bpm": int(round(float(tempo))),
            "beats": len(beat_map),
            "energy_frames": len(energy_map),
        },
    )

    return AudioAnalysisResult(
        duration_ms=duration_ms,
        bpm=int(round(float(tempo))),
        beat_map=beat_map,
        energy_map=energy_map,
    )