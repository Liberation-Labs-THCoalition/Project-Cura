"""FS-894bdf34026e — an empty hour answer bricks setup permanently, with a traceback.

to_hour24() assumes its regex matched. The window wizard stores "" for the
morning/evening questions when the box is cleared (gui.go_next only validates
non-empty values, and neither hour question is `required`), and both wizards
share ~/.cura/setup-progress.json. On the next run the terminal wizard's `ask`
returns the stored "" without re-asking, to_hour24("") raises AttributeError,
no config is written, and "completed" is never set -- so `cura rehearse` and
`cura add-phone` both refuse forever. Every subsequent run fails identically,
and the caregiver is shown the stack trace the design promises he never sees.
"""
import json, pathlib
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

PROGRESS = {
    "name": "Margaret Chen", "preferred_name": "Margaret", "phone": "307-555-0101",
    "morning": "", "evening": "7pm", "caregiver_name": "Bob Chen",
    "caregiver_phone": "307-555-0199", "meds": "Lisinopril", "address": "",
}


def test_empty_hour_does_not_crash_setup(tmp_path):
    d = tmp_path / ".cura"
    d.mkdir(parents=True)
    (d / "setup-progress.json").write_text(json.dumps(PROGRESS))

    r = run_cura(["setup"], tmp_path, "\n")

    assert "Traceback" not in r.stderr, (
        "setup died with a stack trace on a stored empty hour:\n" + r.stderr[-600:]
    )
    configs = [f for f in d.glob("*.json") if f.name != "setup-progress.json"]
    assert configs, "setup produced no config, so Cura cannot be run at all"
    assert json.loads((d / "setup-progress.json").read_text()).get("completed"), (
        "setup never completes, so `cura rehearse` and `cura add-phone` both refuse"
    )
