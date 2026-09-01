"""FS-fbefe09ff9e9 — cura/setup/ has no tests at all.

The setup package (wizard.py, gui.py, preview.py, add_phone.py — 976 lines) is
the newest code in the tree and the only code the caregiver ever operates by
hand. Nothing in tests/ imports it. Every config Cura later dials, every
medication time, every caregiver number originates here, and the 157-test suite
reports green whether these files work or do not exist.

Replayed hermetically: the tree is copied to a temp directory, each setup module
is replaced by a module that raises on import, and the full suite is run against
the copy. A suite that exercises setup at all must go red. Nothing under
/home/asdf/Project-Cura is modified.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

SETUP_MODULES = [
    "cura/setup/wizard.py",
    "cura/setup/gui.py",
    "cura/setup/preview.py",
    "cura/setup/add_phone.py",
]


def _stage(tmp: Path) -> None:
    for part in ("cura", "tests"):
        shutil.copytree(REPO / part, tmp / part,
                        ignore=shutil.ignore_patterns("__pycache__"))


def _run_suite(tmp: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
        cwd=tmp, capture_output=True, text=True,
    )


def test_no_test_file_even_imports_the_setup_package():
    referencing = [p.name for p in sorted((REPO / "tests").glob("test_*.py"))
                   if "cura.setup" in p.read_text() or "cura/setup" in p.read_text()]
    assert referencing, (
        "no file in tests/ references cura.setup — the wizard, the setup window, "
        "the rehearsal printer and the Twilio onboarding step are entirely untested"
    )


def test_suite_notices_when_the_setup_package_is_broken(tmp_path):
    survivors = []
    for rel in SETUP_MODULES:
        work = tmp_path / Path(rel).stem
        work.mkdir()
        _stage(work)
        (work / rel).write_text(
            'raise RuntimeError("SABOTAGED: %s")\n' % rel)
        if _run_suite(work).returncode == 0:
            survivors.append(rel)

    assert not survivors, (
        "the whole suite stays green with these files replaced by a hard crash: "
        + ", ".join(survivors)
    )
