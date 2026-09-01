"""FS-e563f4667178 — the runner prints "check-in sent" for calls that were never placed.

_run_scheduled's morning_job/evening_job await voice.call() and then print
"Morning check-in sent to <name>" unconditionally. CallResult.answered and
CallResult.error are discarded. Nothing is logged, nothing is retried and the
caregiver is not told. The daily line on his screen says the call went out on
exactly the days it did not.
"""
import json, sys, types
from datetime import datetime, timezone
import pytest
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

CONFIG = {
    "name": "Margaret Chen", "preferred_name": "Margaret", "phone": "+13075550101",
    "medications": [{"name": "Lisinopril", "time": "morning"}],
    "emergency_contacts": [{"name": "Bob", "phone": "+13075550199", "relation": "caregiver"}],
    "primary_caregiver": {"name": "Bob", "phone": "+13075550199"},
    "morning_time": 8, "evening_time": 19,
    "twilio": {"account_sid": "AC0", "auth_token": "t", "phone_number": "+13075550123"},
}


@pytest.fixture
def fake_scheduler(monkeypatch):
    fired = []

    class FakeScheduler:
        def add_job(self, fn, *a, **k):
            fired.append(fn)

        def start(self):
            fired[0]()          # the morning job
            raise KeyboardInterrupt

    mod = types.ModuleType("apscheduler.schedulers.blocking")
    mod.BlockingScheduler = FakeScheduler
    monkeypatch.setitem(sys.modules, "apscheduler", types.ModuleType("apscheduler"))
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers", types.ModuleType("apscheduler.schedulers"))
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.blocking", mod)
    return fired


def test_failed_call_is_not_reported_as_sent(tmp_path, capsys, monkeypatch, fake_scheduler):
    from cura.comms.voice import CallResult, CuraVoice

    async def failing_call(self, to_number, messages, **kw):
        return CallResult(timestamp=datetime.now(timezone.utc), to_number=to_number,
                          answered=False,
                          error="HTTP 401 error: Authentication Error - No credentials provided")

    monkeypatch.setattr(CuraVoice, "call", failing_call)

    path = tmp_path / "margaret.json"
    path.write_text(json.dumps(CONFIG))

    from cura.__main__ import _run_scheduled
    _run_scheduled(str(path), dry_run=False)

    out = capsys.readouterr().out
    assert "check-in sent" not in out, (
        "the call failed with a 401 and the runner still printed "
        "'Morning check-in sent to Margaret' -- the caregiver's only signal "
        "that Cura is working reports success for a call that never happened"
    )
