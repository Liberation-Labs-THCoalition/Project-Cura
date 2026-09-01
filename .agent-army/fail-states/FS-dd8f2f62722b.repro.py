"""FS-dd8f2f62722b — cura/comms/webhook.py has no tests.

webhook.py is the only place the elder's answer comes back into Cura. Every
keypad press during a check-in, every inbound call she places herself, and every
Twilio call-status callback lands in create_app()'s routes. Nothing in tests/
imports it, and the full suite stays green with the module replaced by a hard
crash — so "the elder pressed 2 and asked for help" is a path the 157 tests have
never executed once.

Replayed hermetically in a temp copy; nothing under /home/asdf/Project-Cura is
modified.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TARGET = "cura/comms/webhook.py"


def test_no_test_file_references_the_webhook():
    referencing = [p.name for p in sorted((REPO / "tests").glob("test_*.py"))
                   if "webhook" in p.read_text()]
    assert referencing, (
        "no file in tests/ references cura.comms.webhook — the routes that "
        "receive the elder's keypad answer are untested"
    )


def test_suite_notices_when_the_webhook_is_broken(tmp_path):
    for part in ("cura", "tests"):
        shutil.copytree(REPO / part, tmp_path / part,
                        ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / TARGET).write_text('raise RuntimeError("SABOTAGED: %s")\n' % TARGET)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert proc.returncode != 0, (
        "the whole suite passes with cura/comms/webhook.py replaced by a hard "
        "crash: " + proc.stdout.strip().splitlines()[-1]
    )
