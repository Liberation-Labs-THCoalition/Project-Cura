"""FS-52806d97fbb8 — a bare hour is silently read as AM, so the evening call lands at 7am.

an_hour() accepts "7" with no meridiem and to_hour24() maps it to 07:00. Answering
the evening question with a bare "7" -- the obvious shorthand when the question
already says "evening" -- schedules both check-ins in the morning. The evening
check-in, and with it every evening medication prompt, never happens. The config
records evening_time: 7 and nothing warns.
"""
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

ANSWERS = ["Margaret Chen", "", "307-555-0101", "8", "7",
           "Bob Chen", "307-555-0199", "Lisinopril", ""]


def test_evening_checkin_is_not_scheduled_before_the_morning_one(tmp_path):
    run_cura(["setup"], tmp_path, "\n".join(ANSWERS) + "\n")
    cfg = written_config(tmp_path)
    assert cfg["evening_time"] > cfg["morning_time"], (
        f"morning_time={cfg['morning_time']} evening_time={cfg['evening_time']}: "
        "the bare hour '7' was taken as 7am, so there is no evening check-in")
