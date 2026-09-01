"""FS-15f837197b69 — Cura promises to alert the family and alerts no one.

Both production call sites build the responder bare -- cura/__main__.py:106
(`responder = CuraResponder()`) and cura/comms/webhook.py:189 -- so
on_help_requested is None. CuraVoice.alert_caregiver and CuraVoice.crisis_alert
are defined and are called from nowhere in the package. Pressing 2, or saying
"I fell", still plays "I'm letting your family know right now."
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

PROMISES = ("letting your family know", "alerting your family", "contacting your family")


def _promises_alert(say):
    return any(p in say.lower() for p in PROMISES)


def test_production_responder_can_actually_alert():
    from cura.comms.responder import CuraResponder
    r = CuraResponder()          # exactly as cura/__main__.py:106 constructs it
    said = r.handle_dtmf("2", "checkin")["say"]
    assert not (_promises_alert(said) and r._on_help is None), (
        "the elder is told 'I'm letting your family know right now' while no "
        "handler is wired, so no call, text or record of the request exists: " + said
    )


def test_spoken_distress_reaches_the_caregiver():
    from cura.comms.responder import CuraResponder
    r = CuraResponder()
    said = r.handle_speech("I fell in the pantry and I can't get up", "checkin")["say"]
    assert not (_promises_alert(said) and r._on_help is None), (
        "a reported fall is answered with 'Help is on the way' and goes nowhere: " + said
    )


def test_some_shipped_code_wires_the_escalation():
    import pathlib
    hits = []
    for p in (ROOT / "cura").rglob("*.py"):
        text = p.read_text(errors="ignore")
        if "on_help_requested=" in text or "alert_caregiver(" in text and "async def" not in text.split("alert_caregiver(")[0][-40:]:
            hits.append(p.name)
    assert hits, (
        "nothing outside the test suite ever supplies on_help_requested or calls "
        "alert_caregiver -- the escalation path is unreachable in the shipped product"
    )
