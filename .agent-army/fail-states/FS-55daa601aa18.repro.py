"""FS-55daa601aa18 — the caregiver's number is accepted when it is the elder's own.

Nothing compares the two numbers. In a shared-landline household -- the common
case when the caregiver lives with the person being called -- every escalation,
alert and crisis text is addressed to the same handset Cura just called, and the
caregiver has no separate channel. The alert script also reads the crisis details
aloud to whoever answers, which in this household is the person in crisis.
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

SAME = "307-555-0101"
ANSWERS = ["Margaret Chen", "", SAME, "8am", "7pm", "Bob Chen", SAME, "Lisinopril", ""]


def test_caregiver_number_must_differ_from_the_elder(tmp_path):
    run_cura(["setup"], tmp_path, "\n".join(ANSWERS) + "\n")
    cfg = written_config(tmp_path)
    assert cfg["primary_caregiver"]["phone"] != cfg["phone"], (
        "setup accepted the elder's own number as the caregiver's without a word; "
        "escalation now dials the person it is escalating about")
