"""`cura rehearse` must tell a caregiver what Cura is NOT handling.

Phase 2 of rollout C2 makes `cura rehearse` (cura/__main__.py::_preview) print,
under a "Cura is NOT handling:" heading, the gaps returned by
cura.readiness.readiness_gaps(config_path). It imports cura.readiness INSIDE
_preview only, and if readiness_gaps raises, rehearse prints one line saying so
and still prints both check-ins; it never raises.

These tests are written first (red). Tests 1-3 fail until _preview learns to
report gaps; test 4 (no import cycle) may already pass.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_production_seam import _wizard_config


def _no_weather(monkeypatch):
    """_weather fetches real weather over the network; stub it out."""
    import cura.__main__ as cura_main
    monkeypatch.setattr(cura_main, "_weather", lambda config_path: None)


def test_rehearse_names_the_missing_dispatch_line(tmp_path, capsys, monkeypatch):
    """A config with no dispatch line must be named as a gap."""
    _no_weather(monkeypatch)
    from cura.__main__ import _preview
    _preview(str(_wizard_config(tmp_path, dispatch=False)))
    out = capsys.readouterr().out
    assert "Cura is NOT handling" in out
    assert "no monitoring service or dispatch line on file" in out


def test_rehearse_with_a_dispatch_line_omits_that_warning(tmp_path, capsys, monkeypatch):
    """A config that HAS a dispatch line must not be warned about one."""
    _no_weather(monkeypatch)
    from cura.__main__ import _preview
    _preview(str(_wizard_config(tmp_path, dispatch=True)))
    out = capsys.readouterr().out
    assert "no monitoring service or dispatch line on file" not in out


def test_rehearse_still_prints_both_checkins_when_the_gap_check_fails(
        tmp_path, capsys, monkeypatch):
    """If readiness_gaps raises, rehearse says so and still prints both
    check-ins; it never raises."""
    _no_weather(monkeypatch)
    import cura.__main__ as cura_main
    import cura.readiness as readiness
    monkeypatch.setattr(readiness, "readiness_gaps",
                        lambda config_path: (_ for _ in ()).throw(
                            RuntimeError("boom")))
    from cura.__main__ import _preview
    # Must not raise.
    _preview(str(_wizard_config(tmp_path, dispatch=False)))
    out = capsys.readouterr().out
    assert "In the morning" in out
    assert "In the evening" in out
    assert "readiness check failed" in out


def test_the_two_modules_import_each_other_without_a_cycle():
    """cura.__main__ and cura.readiness must import in either order, in a
    fresh process, without a circular-import failure."""
    for order in ("import cura.__main__, cura.readiness",
                  "import cura.readiness, cura.__main__"):
        proc = subprocess.run(
            [sys.executable, "-c", order],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
        )
        assert proc.returncode == 0, (
            f"{order!r} failed (exit {proc.returncode}):\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
