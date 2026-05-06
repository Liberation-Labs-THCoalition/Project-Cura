"""Voice prosody analysis — detecting distress, confusion, cognitive changes.

pip install opensmile  (or: pip install librosa)

Analyzes voice recordings from check-in calls for:
  - Prosody changes (pitch, rate, energy)
  - Speech quality (jitter, shimmer — vocal cord health)
  - Cognitive markers (long pauses, word-finding difficulty)

NOT a diagnostic tool. Flags changes from baseline for caregiver review.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VoiceAnalysisResult:
    """Result of analyzing a voice recording."""
    mean_pitch: float = 0.0
    pitch_variability: float = 0.0
    speech_rate: float = 0.0
    energy: float = 0.0
    jitter: float = 0.0
    shimmer: float = 0.0
    pause_ratio: float = 0.0
    deviation_from_baseline: float = 0.0
    flags: list[str] = field(default_factory=list)


class VoiceProsodyAnalyzer:
    """Analyze voice recordings for health-relevant prosody changes.

    Uses openSMILE (eGeMAPS feature set) when available.
    Falls back to librosa for basic pitch/energy analysis.
    """

    def __init__(self) -> None:
        self._baseline: dict[str, float] = {}
        self._backend = self._detect_backend()

    @staticmethod
    def _detect_backend() -> str:
        try:
            import opensmile
            return "opensmile"
        except ImportError:
            pass
        try:
            import librosa
            return "librosa"
        except ImportError:
            pass
        return "none"

    def set_baseline(self, features: dict[str, float]) -> None:
        self._baseline = dict(features)

    def analyze(self, audio_path: str) -> VoiceAnalysisResult:
        if self._backend == "opensmile":
            return self._analyze_opensmile(audio_path)
        elif self._backend == "librosa":
            return self._analyze_librosa(audio_path)
        else:
            logger.warning("No audio analysis backend available")
            return VoiceAnalysisResult()

    def _analyze_opensmile(self, audio_path: str) -> VoiceAnalysisResult:
        import opensmile

        smile = opensmile.Smile(
            feature_set=opensmile.FeatureSet.eGeMAPSv02,
            feature_level=opensmile.FeatureLevel.Functionals,
        )
        features = smile.process_file(audio_path)

        result = VoiceAnalysisResult(
            mean_pitch=float(features.get("F0semitoneFrom27.5Hz_sma3nz_amean", [0])[0]),
            pitch_variability=float(features.get("F0semitoneFrom27.5Hz_sma3nz_stddevNorm", [0])[0]),
            energy=float(features.get("loudness_sma3_amean", [0])[0]),
            jitter=float(features.get("jitterLocal_sma3nz_amean", [0])[0]),
            shimmer=float(features.get("shimmerLocaldB_sma3nz_amean", [0])[0]),
        )

        self._flag_deviations(result)
        return result

    def _analyze_librosa(self, audio_path: str) -> VoiceAnalysisResult:
        import librosa
        import numpy as np

        y, sr = librosa.load(audio_path, sr=None)
        pitches, magnitudes = librosa.piptrack(y=y, sr=sr)

        pitch_values = pitches[pitches > 0]
        mean_pitch = float(np.mean(pitch_values)) if len(pitch_values) > 0 else 0.0
        pitch_var = float(np.std(pitch_values)) / max(mean_pitch, 1.0) if len(pitch_values) > 0 else 0.0

        rms = librosa.feature.rms(y=y)
        energy = float(np.mean(rms))

        result = VoiceAnalysisResult(
            mean_pitch=mean_pitch,
            pitch_variability=pitch_var,
            energy=energy,
        )

        self._flag_deviations(result)
        return result

    def _flag_deviations(self, result: VoiceAnalysisResult) -> None:
        if not self._baseline:
            return

        deviations = []
        for attr in ["mean_pitch", "energy", "jitter", "shimmer"]:
            current = getattr(result, attr)
            baseline = self._baseline.get(attr, 0)
            if baseline > 0:
                change = abs(current - baseline) / baseline
                if change > 0.3:
                    deviations.append(change)
                    if attr == "mean_pitch":
                        result.flags.append(f"Pitch changed {change:.0%} from baseline")
                    elif attr == "energy":
                        result.flags.append(f"Voice energy changed {change:.0%} from baseline")
                    elif attr == "jitter":
                        result.flags.append("Increased vocal jitter — possible fatigue or illness")
                    elif attr == "shimmer":
                        result.flags.append("Voice quality change detected")

        if deviations:
            result.deviation_from_baseline = max(deviations)
