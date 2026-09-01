"""FS-2af3721abf6f — a sentence answer to the medication question becomes drug names.

The wizard splits the medication answer on commas and stores each fragment as a
medication name, with no check that a fragment looks like a drug. A tired
caregiver answering in prose -- which the question invites, since it is phrased
as a yes/no -- produces entries like "He takes Lisinopril every morning and
Metformin with dinner", read aloud verbatim as
"It's time for your He takes Lisinopril every morning and Metformin with dinner
and and Tylenol when her hip hurts."
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

PROSE = ("He takes Lisinopril every morning and Metformin with dinner, "
         "and Tylenol when her hip hurts")
ANSWERS = ["Margaret Chen", "", "307-555-0101", "8am", "7pm",
           "Bob Chen", "307-555-0199", PROSE, ""]


def test_prose_medication_answer_is_not_taken_as_drug_names(tmp_path):
    run_cura(["setup"], tmp_path, "\n".join(ANSWERS) + "\n")
    names = [m["name"] for m in written_config(tmp_path)["medications"]]
    bad = [n for n in names if len(n.split()) > 3 or len(n) > 30]
    assert not bad, (
        "sentence fragments were stored as medication names and will be spoken "
        "aloud as a dosing prompt: " + repr(bad))
