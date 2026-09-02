"""The timing the caregiver wrote must survive into the config.

Four independent review lenses converged on one defect: every entry point
hardcoded {"time": "morning"}. Three consequences, in increasing order of harm:

  1. The whole weekly/PRN model was unreachable — dead code.
  2. An as-needed opioid and a once-weekly bisphosphonate were announced daily
     to a woman with late-stage dementia, who cannot check whether she already
     took them and so believes the reminder.
  3. Both caregiver-warning lists reported ALL CLEAR, because a fabricated
     timing does not look unknown. That is the governing law of this codebase:
     a check that cannot fail is indistinguishable from a check that passed.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from cura.pulse.eldercare_pulse import (ElderProfile, EldercarePulseConfig,
                                        unknown_timing_medications)
from cura.pulse.medication import (Schedule, needs_clarification,
                                   parse_medication, parse_medication_list,
                                   split_medication)

REPO = Path(__file__).resolve().parent.parent


class TestTimingIsNeverFabricated:
    PRODUCTION = ["cura/setup/wizard.py", "cura/setup/gui.py",
                  "cura/console.py", "cura_mcp_server.py"]

    @pytest.mark.parametrize("rel", PRODUCTION)
    def test_no_module_invents_a_medication_time(self, rel):
        """An invented timing is announced as fact."""
        src = (REPO / rel).read_text()
        assert '"time": "morning"' not in src
        assert "'time': 'morning'" not in src

    @pytest.mark.parametrize("rel", PRODUCTION)
    def test_no_module_hardcodes_any_literal_timing(self, rel):
        """Guard the shape, not just the one string that was there."""
        tree = ast.parse((REPO / rel).read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = [k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            if "time" not in keys:
                continue
            val = node.values[keys.index("time")]
            assert not (isinstance(val, ast.Constant) and val.value), (
                f"{rel} hardcodes a medication time: {ast.dump(val)}")


class TestSplittingNameFromTiming:
    @pytest.mark.parametrize("entry,name,schedule", [
        ("Oxycodone as needed for pain", "Oxycodone", Schedule.PRN),
        ("Alendronate on Sundays", "Alendronate", Schedule.WEEKLY),
        ("Warfarin at bedtime", "Warfarin", Schedule.DAILY),
        ("Lisinopril in the morning", "Lisinopril", Schedule.DAILY),
        ("Metoprolol twice daily", "Metoprolol", Schedule.DAILY),
        ("Fosamax every Thursday", "Fosamax", Schedule.WEEKLY),
        ("Tylenol every 6 hours as needed", "Tylenol", Schedule.PRN),
        ("Donepezil", "Donepezil", Schedule.UNKNOWN),
    ])
    def test_the_timing_he_wrote_is_kept(self, entry, name, schedule):
        med = split_medication(entry)
        assert med["name"] == name
        assert parse_medication(med).schedule is schedule

    def test_a_drug_named_after_a_time_of_day_is_not_split(self):
        """"Evening Primrose Oil" must stay a name. A mis-split name attached
        to a confident daily reminder is worse than a question."""
        assert split_medication("Evening Primrose Oil")["name"] == \
            "Evening Primrose Oil"

    def test_a_stranded_preposition_goes_with_the_timing(self):
        assert split_medication("Alendronate on Sundays")["name"] == "Alendronate"

    def test_a_comma_inside_a_timing_phrase_is_not_a_separator(self):
        meds = parse_medication_list(
            "Tylenol every 6 hours as needed, no more than 4 in 24 hours")
        assert len(meds) == 1
        assert parse_medication(meds[0]).max_per_day == 4


class TestTheHouseholdOutcome:
    RAW = ("Oxycodone as needed for pain, Alendronate on Sundays, "
           "Warfarin at bedtime, Donepezil in the morning")

    def _profile(self):
        return ElderProfile(name="Margaret Chen", preferred_name="Margaret",
                            medications=parse_medication_list(self.RAW))

    def test_the_opioid_is_never_announced(self):
        cfg = EldercarePulseConfig(profile=self._profile())
        for slot in ("morning", "evening"):
            assert "Oxycodone" not in cfg.generate_medication_reminder(slot)

    def test_the_weekly_drug_is_not_announced_daily(self):
        cfg = EldercarePulseConfig(profile=self._profile())
        assert "Alendronate" not in cfg.generate_medication_reminder("morning")

    def test_the_bedtime_drug_moves_to_the_evening(self):
        cfg = EldercarePulseConfig(profile=self._profile())
        assert "Warfarin" in cfg.generate_medication_reminder("evening")
        assert "Warfarin" not in cfg.generate_medication_reminder("morning")

    def test_the_guards_do_not_report_all_clear(self):
        """The fabricated config made both lists return [] on a medicine
        cabinet about which nothing was known."""
        meds = parse_medication_list(self.RAW)
        assert needs_clarification(meds), "no clarification asked at all"
        names = {n for n, _ in needs_clarification(meds)}
        assert "Oxycodone" in names       # no dosing interval recorded
        assert "Alendronate" in names     # weekly, but no time of day

    def test_the_old_fabricated_config_would_have_failed_these(self):
        """Pin the regression: the shape that shipped before must not pass."""
        fabricated = [{"name": n, "time": "morning"} for n in
                      ("Oxycodone as needed for pain", "Alendronate on Sundays",
                       "Warfarin at bedtime", "Donepezil")]
        cfg = EldercarePulseConfig(profile=ElderProfile(
            name="M", preferred_name="M", medications=fabricated))
        spoken = cfg.generate_medication_reminder("morning")
        assert "Oxycodone" in spoken and "Alendronate" in spoken
        assert unknown_timing_medications(fabricated) == []
        assert needs_clarification(fabricated) == []


class TestEntrypointsAreWired:
    def test_webhook_passes_the_auth_token_to_create_app(self):
        """create_app refuses to build without a token, by design. The one
        production call site never passed one, so `cura webhook` could not
        start on any config — two halves, both correct, never joined."""
        src = (REPO / "cura/__main__.py").read_text()
        tree = ast.parse(src)
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call)
                 and getattr(n.func, "id", "") == "create_app"]
        assert calls, "no create_app call site found"
        for c in calls:
            kw = {k.arg for k in c.keywords}
            assert "auth_token" in kw, "create_app called without auth_token"

    def test_both_check_ins_offer_a_way_to_answer(self):
        """do_evening requested a Gather but passed no action URL, so
        _build_twiml correctly refused to emit it and the evening call was
        speech-only — nothing listening when she asks for help."""
        src = (REPO / "cura/__main__.py").read_text()
        tree = ast.parse(src)
        for fn in ("do_morning", "do_evening"):
            node = next(n for n in ast.walk(tree)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and n.name == fn)
            calls = [c for c in ast.walk(node) if isinstance(c, ast.Call)]
            gathers = [c for c in calls
                       if any(k.arg == "gather_response" for k in c.keywords)]
            assert gathers, f"{fn} places no gathering call"
            for g in gathers:
                kw = {k.arg for k in g.keywords}
                assert "gather_action" in kw, f"{fn} gathers with no action URL"
