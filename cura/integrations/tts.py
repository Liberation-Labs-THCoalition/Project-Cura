"""Local TTS via Piper — warm, natural voice for offline use.

pip install piper-tts

Generates audio files from text for:
  - Local playback (tablet/speaker mode)
  - Pre-recording messages for phone delivery
  - Backup when Twilio TTS is unavailable

Runs entirely on CPU — no cloud dependency.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class LocalTTS:
    """Generate speech audio using Piper TTS.

    Args:
        voice: Piper voice model name (default: warm female US English)
        output_dir: Directory for generated audio files
    """

    def __init__(
        self,
        voice: str = "en_US-lessac-medium",
        output_dir: str = "/tmp/cura_audio",
    ) -> None:
        self._voice = voice
        self._output_dir = Path(output_dir)
        self._available = self._check_available()

    @staticmethod
    def _check_available() -> bool:
        try:
            import piper
            return True
        except ImportError:
            logger.info("piper-tts not installed — local TTS unavailable")
            return False

    @property
    def available(self) -> bool:
        return self._available

    def synthesize(self, text: str, filename: str = "output.wav") -> Path | None:
        if not self._available:
            return None

        self._output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self._output_dir / filename

        try:
            import piper
            voice = piper.PiperVoice.load(self._voice)
            with open(out_path, "wb") as f:
                voice.synthesize(text, f)
            return out_path
        except Exception as e:
            logger.error("TTS synthesis failed: %s", e)
            return None

    def synthesize_checkin(self, messages: list[str], filename: str = "checkin.wav") -> Path | None:
        combined = " ... ".join(messages)
        return self.synthesize(combined, filename)
