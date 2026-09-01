"""FS-a1e7a98e96ad — synthesised check-in audio goes to a shared /tmp directory.

    def __init__(self, voice="en_US-lessac-medium", output_dir="/tmp/cura_audio"):

and synthesize() does self._output_dir.mkdir(parents=True, exist_ok=True) with no
mode, then writes checkin.wav.

/tmp is world-writable and shared between every account on the machine. Two
consequences, both from the fixed, predictable path:

  1. If /tmp/cura_audio does not exist yet, it is created at the umask default
     (0755) and every file in it is readable by every account. Those files are
     recordings of the check-in script: "Just a reminder -- it's time for your
     Lisinopril and Metformin." That is the medication list, spoken aloud, in a
     shared directory.
  2. If /tmp/cura_audio already exists -- created by another account, or left as
     a symlink -- exist_ok=True accepts it and writes through it. The path is
     fixed and guessable, so it can be planted before Cura ever runs.

This is rated low, not high, because Piper is optional and unlisted in both
requirements files, so on the first household this code path does not execute.
It becomes real the moment local TTS is switched on. The fix is the same shape
as everywhere else in Cura: default to ~/.cura/audio, mkdir with mode 0o700.

RED = the default audio directory is under a shared temp root.
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from cura.integrations.tts import LocalTTS


def test_default_audio_directory_is_not_in_shared_tmp():
    default_dir = pathlib.Path(LocalTTS()._output_dir).resolve()
    shared = pathlib.Path(tempfile.gettempdir()).resolve()
    assert shared not in default_dir.parents and default_dir != shared, (
        f"LocalTTS writes spoken check-ins -- which name the resident's "
        f"medications -- to {default_dir}, under the shared temp directory. "
        "The path is fixed, so another account can pre-create or symlink it."
    )


def test_audio_directory_is_created_private():
    with tempfile.TemporaryDirectory() as td:
        target = pathlib.Path(td) / "cura_audio"
        tts = LocalTTS(output_dir=str(target))
        tts._output_dir.mkdir(parents=True, exist_ok=True)   # what synthesize() does
        mode = target.stat().st_mode & 0o777
        assert not (mode & 0o077), (
            f"the audio directory is created {oct(mode)}; the check-in audio "
            "inside names her medications."
        )
