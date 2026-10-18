"""Tests for cura.readiness.readiness_gaps.

``readiness_gaps(config_path) -> list[str]`` is the plain-language list of what
Cura is NOT handling for a household, so a caregiver can see it. It composes
checks that already exist:

  * ``cura.comms.escalation.escalation_readiness(profile)``
  * ``Household.blocking_problems()`` and ``Household.reportable_gaps()``
    (from ``cura/household/__init__.py``, loaded via
    ``cura.__main__._load_household``, which returns ``None`` for a legacy
    config that predates the household block)
  * ``cura.pulse.eldercare_pulse.unknown_timing_medications(medications)``,
    one line per medication: "Cura does not know when {name} is taken and will
    not name it"

A config with no elder in it (no name and no phone, such as ``config/VALUES.json``)
returns exactly ``["no elder config loaded"]``.

These tests are written FIRST (phase 1 of 2). ``cura.readiness`` does not exist
yet, so every test here is expected to fail (import error) until phase 2 writes
the module. The tests must not be touched by phase 2.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.test_production_seam import _wizard_config


REPO_ROOT = Path(__file__).resolve().parent.parent


class TestReadinessGaps:
    def test_no_dispatch_line_is_reported(self, tmp_path):
        """No monitoring service or dispatch line: the ladder ends inside the house, and the caregiver is told."""
        from cura.readiness import readiness_gaps

        gaps = readiness_gaps(str(_wizard_config(tmp_path, dispatch=False)))
        assert any("no monitoring service or dispatch line on file" in g for g in gaps), gaps

    def test_a_dispatch_line_removes_that_warning(self, tmp_path):
        """With a dispatch line on file there is a rung outside the household, so that warning is gone."""
        from cura.readiness import readiness_gaps

        gaps = readiness_gaps(str(_wizard_config(tmp_path, dispatch=True)))
        assert not any("no monitoring service or dispatch line on file" in g for g in gaps), gaps

    def test_the_sole_caregiver_gap_stays_with_a_dispatch_line(self, tmp_path):
        """"If Ray is the one who needs help, there is nobody else for Cura to call" is a different gap: the sole
        caregiver inside the household. A dispatch line doesn't answer it, and the report must not hide it. (The
        rollout spec's test conflated the two warnings; the first build then filtered this one out to pass. CC's
        review, 2026-10-17.)"""
        from cura.readiness import readiness_gaps

        gaps = readiness_gaps(str(_wizard_config(tmp_path, dispatch=True)))
        assert any("nobody else for Cura to call" in g for g in gaps), gaps

    def test_a_medication_without_a_time_is_reported(self, tmp_path):
        """A medication with no recorded time is reported as something Cura will
        not name, so the caregiver knows it is not being reminded about it.
        Silence is safe for dosing and unsafe for trust."""
        from cura.readiness import readiness_gaps

        cfg = _wizard_config(tmp_path)
        data = json.loads(Path(cfg).read_text())
        # A medication named but with no time, shaped as the wizard stores it.
        med = [{"name": "Lisinopril 10mg"}]
        # Set it both at the top level (where _build_responder / _preview read
        # the profile from) and on the elder member (where profile_for reads it),
        # so the test holds regardless of which projection readiness_gaps uses.
        data["medications"] = med
        for m in data["household"]["members"]:
            if m.get("member_id") == "margaret":
                m["medications"] = med
        Path(cfg).write_text(json.dumps(data))

        gaps = readiness_gaps(str(cfg))
        assert any("Cura does not know when" in g and "Lisinopril" in g
                   for g in gaps), (
            "expected a 'Cura does not know when ... Lisinopril ...' line for a "
            f"medication with no time; got: {gaps!r}")

    def test_a_legacy_config_without_a_household_does_not_raise(self, tmp_path):
        """A config that predates the household block (no 'household' key) must
        not raise. _load_household returns None for it, and readiness_gaps must
        still return a list of plain-language gaps."""
        from cura.readiness import readiness_gaps

        cfg = {
            "name": "Margaret Chen",
            "phone": "+13075550134",
            "emergency_contacts": [
                {"name": "Ray Chen", "phone": "+13075550199",
                 "relation": "caregiver"},
            ],
            "primary_caregiver": {"name": "Ray Chen", "phone": "+13075550199"},
        }
        p = tmp_path / "legacy.json"
        p.write_text(json.dumps(cfg))

        gaps = readiness_gaps(str(p))
        assert isinstance(gaps, list)

    def test_values_json_is_not_an_elder_config(self):
        """config/VALUES.json has no elder in it (no name, no phone), so
        readiness_gaps reports exactly that and nothing else."""
        from cura.readiness import readiness_gaps

        values = REPO_ROOT / "config" / "VALUES.json"
        gaps = readiness_gaps(str(values))
        assert gaps == ["no elder config loaded"]

    def test_the_function_dials_nothing(self, tmp_path, monkeypatch):
        """readiness_gaps is a read-only report. It must not dial: monkeypatch
        the dispatcher script (the one function that builds the words spoken to a
        911 dispatcher) to raise, and assert readiness_gaps still returns
        normally. If it ever reached the dial path it would raise here."""
        from cura.readiness import readiness_gaps
        from cura.comms import ladder

        def _boom(*args, **kwargs):
            raise AssertionError("dialled")

        monkeypatch.setattr(ladder, "dispatch_script", _boom)

        cfg = _wizard_config(tmp_path)
        gaps = readiness_gaps(str(cfg))
        assert isinstance(gaps, list)

        # Belt and suspenders: a read-only report must not pull in the dialing
        # library at all. Remove twilio from sys.modules first so a stray import
        # during the call would be visible.
        for mod in list(sys.modules):
            if mod == "twilio" or mod.startswith("twilio."):
                del sys.modules[mod]
        _ = readiness_gaps(str(cfg))
        assert not any(m == "twilio" or m.startswith("twilio.")
                       for m in sys.modules), (
            "readiness_gaps imported twilio; a readiness report must not dial")
