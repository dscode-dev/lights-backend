from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Tuple

import librosa
import numpy as np

log = logging.getLogger("audio.analyzer")


@dataclass
class AudioAnalysisResult:
    duration_ms: int
    bpm: int
    energy_envelope: List[float]   # 0..1
    energy_frame_ms: int           # ex: 20


def _normalize_envelope(env: np.ndarray) -> np.ndarray:
    """
    Normaliza envelope para 0..1 de forma robusta:
    - remove DC/ruído baixo
    - usa percentis para evitar outliers
    - compressão leve para dar "vida" em músicas baixas
    """
    if env.size == 0:
        return env

    env = np.maximum(env, 0.0)

    p10 = float(np.percentile(env, 10))
    p95 = float(np.percentile(env, 95))

    if p95 <= p10 + 1e-9:
        # envelope quase constante
        out = env - p10
        mx = float(out.max()) if out.size else 0.0
        if mx <= 1e-9:
            return np.zeros_like(env)
        out = out / mx
        return np.clip(out, 0.0, 1.0)

    out = (env - p10) / (p95 - p10)
    out = np.clip(out, 0.0, 1.0)

    # compressão (gamma) p/ levantar música baixa sem saturar tudo
    gamma = 0.65
    out = np.power(out, gamma)

    # suaviza um pouco p/ ficar "água"
    # (pequeno filtro de média móvel)
    k = 3
    if out.size >= k:
        kernel = np.ones(k, dtype=np.float32) / float(k)
        out = np.convolve(out, kernel, mode="same")

    return np.clip(out, 0.0, 1.0)


def _compute_rms_envelope(y: np.ndarray, sr: int, frame_ms: int) -> Tuple[np.ndarray, int]:
    """
    RMS por frames fixos (frame_ms).
    Retorna array de energia (float) e hop_length.
    """
    frame_ms = int(frame_ms)
    if frame_ms < 10:
        frame_ms = 10
    if frame_ms > 60:
        frame_ms = 60

    hop_length = int(sr * (frame_ms / 1000.0))
    hop_length = max(128, hop_length)

    # frame_length maior que hop ajuda estabilidade
    frame_length = hop_length * 2

    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length, center=True)[0]
    return rms.astype(np.float32), hop_length


def analyze_audio_file(path: str, *, energy_frame_ms: int = 20) -> AudioAnalysisResult:
    """
    Analisa um WAV local e retorna:
    - duração (ms)
    - BPM global
    - envelope RMS normalizado (0..1)
    - frameMs do envelope
    """
    log.info("audio_load_start", extra={"path": path})

    y, sr = librosa.load(path, sr=None, mono=True)
    log.info("audio_load_ok", extra={"sr": sr, "samples": int(y.shape[0])})

    duration_s = librosa.get_duration(y=y, sr=sr)
    duration_ms = int(duration_s * 1000)

    # BPM (global)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = int(round(float(tempo))) if tempo else 120

    # Envelope RMS
    rms, hop_length = _compute_rms_envelope(y, sr, energy_frame_ms)

    # Normalização robusta 0..1
    env = _normalize_envelope(rms)

    log.info(
        "audio_analysis_ok",
        extra={
            "duration_ms": duration_ms,
            "bpm": bpm,
            "energy_frame_ms": int(energy_frame_ms),
            "envelope_len": int(env.size),
            "hop_length": int(hop_length),
        },
    )

    return AudioAnalysisResult(
        duration_ms=duration_ms,
        bpm=bpm,
        energy_envelope=[float(x) for x in env.tolist()],
        energy_frame_ms=int(energy_frame_ms),
    )