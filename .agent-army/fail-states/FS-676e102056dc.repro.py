"""FS-676e102056dc — running `cura setup` a second time deletes the phone credentials.

wizard.run() rebuilds the config dict from the progress file and overwrites the
config file wholesale. The `twilio` block that `cura add-phone` wrote is not read
and not carried over. Setup re-run asks nothing at all -- it prints
"All set. Cura is ready." in under a second -- so nothing signals the loss.
After this, `cura run` places no calls.
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

SID = "AC" + "0123456789abcdef" * 2
TOKEN = "0123456789abcdef" * 2


def test_setup_rerun_keeps_phone_credentials(tmp_path):
    run_cura(["setup"], tmp_path, "\n".join(ANSWERS) + "\n")
    run_cura(["add-phone"], tmp_path, "\n".join(["", SID, TOKEN, "+13075550123"]) + "\n")
    assert "twilio" in written_config(tmp_path), "add-phone did not write credentials"

    # He is not sure the wizard finished, so he runs it again.
    run_cura(["setup"], tmp_path, "\n")

    cfg = written_config(tmp_path)
    assert "twilio" in cfg, (
        "re-running `cura setup` silently deleted the Twilio credentials; "
        "Cura can no longer place a call and says nothing about it"
    )
    assert cfg["twilio"]["account_sid"] == SID
