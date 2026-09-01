"""FS-2b702d758df4 — spoken text is dropped into TwiML without XML escaping.

_build_twiml interpolates names, medication names and enrichment text straight
into <Say> elements. An ampersand or angle bracket anywhere in the config --
"Vitamin D & calcium", "Ruth & Bill" -- produces a malformed document, Twilio
rejects the call, CuraVoice swallows the error into CallResult.error, and the
runner prints "check-in sent". The phone silently stops ringing.
"""
import sys
import xml.etree.ElementTree as ET
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def run_cura(args, home, stdin_text="", timeout=60):
    """Run `python -m cura ...` against a throwaway HOME, as the caregiver would."""
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
    return subprocess.run([sys.executable, "-m", "cura", *args], cwd=str(ROOT),
                          input=stdin_text, capture_output=True, text=True,
                          env=env, timeout=timeout)


def written_config(home):
    d = pathlib.Path(home) / ".cura"
    files = [f for f in d.glob("*.json") if f.name != "setup-progress.json"]
    assert files, f"setup wrote no config into {d}"
    return json.loads(files[0].read_text())

sys.path.insert(0, str(ROOT))


def test_twiml_stays_well_formed_with_an_ampersand():
    from cura.comms.voice import CuraVoice
    twiml = CuraVoice()._build_twiml(
        ["Good morning, Ruth & Bill.", "It's time for your Vitamin D & calcium."],
        gather=True)
    try:
        ET.fromstring(twiml)
    except ET.ParseError as e:
        raise AssertionError(
            f"TwiML is not well-formed XML ({e}); Twilio rejects the call and "
            f"nobody is told:\n{twiml}") from None
