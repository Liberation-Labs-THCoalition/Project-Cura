"""FS-05a6bd6524af — Flask is in neither requirements file, so `cura webhook` cannot start.

The webhook is the only thing that receives "press 2 if you need help" and the
speech transcript. create_app raises ImportError without Flask, and install.sh
installs requirements-core.txt only. After a by-the-book install there is no way
to run the half of Cura that listens.
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


def test_flask_is_declared_somewhere():
    core = (ROOT / "requirements-core.txt").read_text().lower()
    full = (ROOT / "requirements.txt").read_text().lower()
    assert "flask" in core or "flask" in full, (
        "Flask appears in no requirements file, so `cura webhook` -- the only "
        "path that hears a help request -- cannot be started after install.sh")


def test_flask_is_in_the_core_set_the_installer_uses():
    core = (ROOT / "requirements-core.txt").read_text().lower()
    assert "flask" in core, (
        "install.sh installs requirements-core.txt only; without Flask there "
        "the listening half of Cura is never installed")
