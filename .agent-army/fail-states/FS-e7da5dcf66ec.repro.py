"""FS-e7da5dcf66ec — the escalation tests in tests/test_voice.py cannot fail.

CuraVoice(dry_run=True).call() returns answered=True and call_sid="dry_run"
unconditionally, and send_sms() returns delivered=True unconditionally. Every
assertion in TestDryRunCalls is a read of one of those two constants. None of
them looks at WHO was dialled, so the suite is blind to the one thing the
escalation path exists to do: reach the caregiver.

This is a mutation-escape test. It copies the tree into a temp directory,
breaks CuraVoice so escalation reaches nobody, and runs tests/test_voice.py
against the broken copy. If the suite still passes, the suite is not testing
escalation. Nothing under /home/asdf/Project-Cura is modified.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

MUTANTS = {
    "escalation dials nobody": (
        "cura/comms/voice.py",
        '        caregiver_phone = caregiver.get("phone", "")\n',
        '        caregiver_phone = ""  # MUTANT\n',
    ),
    "crisis alert dials the elder instead of the contacts": (
        "cura/comms/voice.py",
        '        for contact in profile.emergency_contacts:\n            phone = contact.get("phone", "")\n',
        '        for contact in profile.emergency_contacts:\n            phone = getattr(profile, "phone", "")  # MUTANT\n',
    ),
    "morning call names no medication at all": (
        "cura/comms/voice.py",
        '        if hasattr(profile, \'medications\') and profile.medications:\n'
        '            med_names = [m.get("name", "medication") for m in profile.medications[:3]]\n',
        '        if False:\n'
        '            med_names = [m.get("name", "medication") for m in profile.medications[:3]]\n',
    ),
}


def _run_suite_against(tmp: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_voice.py"],
        cwd=tmp, capture_output=True, text=True,
    )


def _stage(tmp: Path) -> None:
    for part in ("cura", "tests"):
        shutil.copytree(REPO / part, tmp / part,
                        ignore=shutil.ignore_patterns("__pycache__"))


def test_voice_suite_baseline_is_green(tmp_path):
    _stage(tmp_path)
    assert _run_suite_against(tmp_path).returncode == 0, "unmutated baseline must pass"


def test_escalation_mutants_are_caught_by_the_voice_suite(tmp_path):
    survivors = []
    for label, (rel, old, new) in MUTANTS.items():
        work = tmp_path / label.replace(" ", "_")
        work.mkdir()
        _stage(work)
        target = work / rel
        text = target.read_text()
        assert old in text, f"anchor for {label!r} no longer present in {rel}"
        target.write_text(text.replace(old, new, 1))
        if _run_suite_against(work).returncode == 0:
            survivors.append(label)

    assert not survivors, (
        "tests/test_voice.py passes against a CuraVoice that "
        + "; ".join(survivors)
        + ". Its assertions read dry-run constants (answered=True, "
          "delivered=True, call_sid='dry_run'), never the number dialled."
    )
