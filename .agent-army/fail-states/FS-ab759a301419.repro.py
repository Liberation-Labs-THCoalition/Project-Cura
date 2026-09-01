"""FS-ab759a301419 — a medication listed twice is named twice in one prompt.

generate_medication_reminder names every entry in the slot with no de-duplication,
and nothing upstream de-duplicates either: typing "Metformin, metformin" (or
listing the same drug twice across two sittings of the wizard) produces
"It's time for your Metformin and metformin." A listener who cannot remember
whether she has already taken it hears two drugs named.
"""
import sys
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


def test_duplicate_medication_is_named_once():
    from cura.pulse.eldercare_pulse import ElderProfile, EldercarePulseConfig
    profile = ElderProfile(
        name="Margaret Chen", preferred_name="Margaret",
        medications=[{"name": "Metformin", "time": "morning"},
                     {"name": "metformin", "time": "morning"}])
    said = EldercarePulseConfig(profile).generate_medication_reminder("morning")
    assert said.lower().count("metformin") == 1, (
        "one drug is named twice in a single dosing prompt: " + repr(said))
