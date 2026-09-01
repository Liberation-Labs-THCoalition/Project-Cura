"""FS-58d4d374e673 — the commands setup tells the caregiver to run do not exist.

`install.sh` creates a venv, installs requirements-core.txt and execs the wizard.
It never installs a launcher. The wizard's closing screen and add_phone's closing
screen instruct the caregiver to run `cura rehearse`, `cura add-phone` and
`cura run --config ...`. None of those is a command, and `python -m cura` only
resolves while the shell happens to be sitting in the repo directory.
`cura run` is what starts the daily calls, so the phone never rings.
"""
import shutil, subprocess, sys, tomllib
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


def _declares_launcher():
    py = ROOT / "pyproject.toml"
    if py.exists():
        data = tomllib.loads(py.read_text())
        scripts = data.get("project", {}).get("scripts", {})
        if "cura" in scripts:
            return True
    if (ROOT / "setup.py").exists() and "console_scripts" in (ROOT / "setup.py").read_text():
        return True
    return any((ROOT / p / "cura").exists() for p in ("bin", "scripts"))


def test_a_cura_launcher_is_installable():
    assert _declares_launcher(), (
        "no console entry point named 'cura' anywhere in the repo, so every "
        "command the wizard tells the caregiver to run is 'command not found'"
    )


def test_b_cura_command_resolves_after_install():
    venv_bin = ROOT / ".venv" / "bin"
    assert (venv_bin / "cura").exists() or shutil.which("cura"), (
        "install.sh finishes without putting a 'cura' command on PATH"
    )


def test_c_module_form_works_from_another_directory():
    r = subprocess.run([sys.executable, "-m", "cura", "--help"],
                       cwd="/tmp", capture_output=True, text=True)
    assert r.returncode == 0, (
        "the fallback the caregiver would be told over the phone, "
        "'python -m cura', fails outside the repo directory: " + r.stderr.strip()
    )
