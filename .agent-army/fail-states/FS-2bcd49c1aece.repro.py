"""FS-2bcd49c1aece — a hand-edited config gives a raw JSONDecodeError traceback.

_preview and _run_scheduled both json.load() the config with no guard. One stray
comma from someone editing the file to correct a phone number ends `cura rehearse`
and `cura run` in a stack trace, with no plain-language statement of what is wrong
or what to do -- the exact failure mode the setup rebuild set out to remove.
"""
import json
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

GOOD = {
    "name": "Margaret Chen", "preferred_name": "Margaret", "phone": "+13075550101",
    "medications": [{"name": "Lisinopril", "time": "morning"}],
    "emergency_contacts": [], "primary_caregiver": {},
    "morning_time": 8, "evening_time": 19,
}


def test_malformed_config_is_explained_not_dumped(tmp_path):
    d = tmp_path / ".cura"
    d.mkdir(parents=True)
    (d / "margaret.json").write_text(json.dumps(GOOD).replace('"morning_time": 8,',
                                                              '"morning_time": 8,,'))
    r = run_cura(["rehearse"], tmp_path, "\n")
    assert "Traceback" not in r.stderr, (
        "rehearse dumped a stack trace at the caregiver:\n" + r.stderr[-400:])
