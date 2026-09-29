"""Does a config the WIZARD writes actually start Cura?

Every other test in this suite verifies a component by handing it inputs
directly. `test_it_is_reached_in_the_sole_caregiver_scenario` asserts
`reached_anyone` for exactly Ray's scenario — by passing `dispatch_line=` into
climb() itself, which is a config the production caller could not supply,
because build_ladder_escalation had no such parameter and __main__ passed one
anyway.

So 750 tests passed while `cura webhook` raised TypeError on every household
config the wizard can write. Each component was verified and nothing owned the
seam between them: Vera's face three, "an integration gap wearing the clothes of
verification."

These tests walk the real path — wizard output, through the real loader, into
the real responder builder — and assert only that it does not explode and does
what the docstrings claim.
"""
from __future__ import annotations

import json

import pytest


def _wizard_config(tmp_path, *, can_answer="no", dispatch=True, twilio=True):
    """A config shaped exactly as cura/setup/wizard.py writes one."""
    from cura.setup.wizard import _household_block
    state = {"name": "Margaret Chen", "preferred_name": "Margaret",
             "phone": "307-555-0134", "caregiver_name": "Ray Chen",
             "caregiver_phone": "307-555-0199", "can_answer": can_answer}
    cfg = {
        "name": "Margaret Chen", "preferred_name": "Margaret",
        "phone": "+13075550134", "morning_time": 8, "evening_time": 20,
        "address": "41 Cottonwood Rd, Buffalo WY", "medications": [],
        "emergency_contacts": [{"name": "Ray Chen", "phone": "+13075550199",
                                "relation": "caregiver"}],
        "primary_caregiver": {"name": "Ray Chen", "phone": "+13075550199"},
    }
    if twilio:
        cfg["twilio"] = {"account_sid": "AC1", "auth_token": "tok",
                         "phone_number": "+15550001111"}
    if dispatch:
        cfg["dispatch_line"] = {"name": "Johnson County dispatch",
                                "phone": "+13075550190"}
    cfg["household"] = _household_block(state, [], cfg)
    p = tmp_path / "margaret.json"
    p.write_text(json.dumps(cfg))
    return p


class TestAWizardConfigStartsCura:
    @pytest.mark.parametrize("can_answer", ["yes", "no"])
    def test_build_responder_does_not_raise(self, tmp_path, can_answer):
        """The whole failure: __main__ passed dispatch_line= to a function
        without that parameter, so this raised TypeError for every config the
        wizard writes, and no test noticed."""
        from cura.__main__ import _build_responder
        cfg = _wizard_config(tmp_path, can_answer=can_answer)
        assert _build_responder(str(cfg)) is not None

    def test_it_works_without_a_dispatch_line_too(self, tmp_path):
        from cura.__main__ import _build_responder
        cfg = _wizard_config(tmp_path, dispatch=False)
        assert _build_responder(str(cfg)) is not None

    def test_the_household_is_the_one_the_wizard_wrote(self, tmp_path):
        from cura.__main__ import _load_household
        h = _load_household(str(_wizard_config(tmp_path)))
        assert h is not None
        assert set(h.members) == {"margaret", "ray_chen"}


class TestEveryClimbParameterCanBeSupplied:
    """climb() grew parameters that build_ladder_escalation never forwarded, so
    rungs that were built and tested could not be reached from production."""

    def test_the_builder_forwards_everything_climb_accepts(self):
        import inspect
        from cura.comms.escalation import build_ladder_escalation
        from cura.comms.ladder import climb
        climb_kw = {p for p, v in inspect.signature(climb).parameters.items()
                    if v.default is not inspect.Parameter.empty}
        builder_kw = set(inspect.signature(build_ladder_escalation).parameters)
        # raised_by is chosen per call, not configured
        missing = climb_kw - builder_kw - {"raised_by"}
        assert not missing, (
            f"climb() accepts {sorted(missing)} that build_ladder_escalation "
            f"cannot supply — those rungs are unreachable from production")

    def test_main_passes_only_what_the_builder_accepts(self):
        """The inverse, which is what actually crashed."""
        import ast
        import inspect
        from pathlib import Path
        from cura.comms.escalation import build_ladder_escalation
        accepted = set(inspect.signature(build_ladder_escalation).parameters)
        src = (Path(__file__).resolve().parent.parent
               / "cura/__main__.py").read_text()
        for call in [c for c in ast.walk(ast.parse(src))
                     if isinstance(c, ast.Call)
                     and getattr(c.func, "id", "") == "build_ladder_escalation"]:
            for kw in call.keywords:
                assert kw.arg in accepted, (
                    f"__main__ passes {kw.arg!r}, which "
                    f"build_ladder_escalation does not accept")


class TestTheAddressReachesTheDispatcher:
    def test_a_dispatcher_call_carries_the_street_address(self, tmp_path):
        """dispatch_script needs the address, and `address` had no parameter to
        travel through — so every dispatcher call would have said "an address I
        do not have on file"."""
        from cura.comms.ladder import climb
        from cura.household import Household, Member, Reach
        spoken = []
        h = Household({
            "margaret": Member("margaret", "Margaret Chen", "Margaret",
                               "+13075550134", Reach.NEVER),
            "ray": Member("ray", "Ray Chen", "Ray", "+13075550199",
                          Reach.SCHEDULED, cares_for=("margaret",))})
        climb(h, "ray", "no movement since 6am",
              send_sms=lambda n, m: False,
              place_call=lambda n, m: (spoken.append((n, m)), False)[1],
              dispatch_line={"name": "dispatch", "phone": "+13075550190"},
              address="41 Cottonwood Rd, Buffalo WY")
        disp = [m for n, m in spoken if n == "+13075550190"]
        assert disp, "the dispatch line was never called"
        assert "41 Cottonwood Rd" in disp[0]
        assert "do not have on file" not in disp[0]


class TestThingsBuiltYesterdayActuallyRun:
    """Three mechanisms were committed yesterday with messages saying they were
    wired. None of them ran: expect_answer had zero production call sites,
    reportable_gaps had zero, and _outside had no writer at all."""

    def test_a_check_in_that_asks_something_records_a_pending_question(
            self, tmp_path, monkeypatch):
        """Without this, record_concern still has no caller and the home safety
        assessment still reports "no concerns identified" forever."""
        from cura.comms import pending
        from cura.__main__ import _remember_question
        from cura.pulse.checkin_composer import CheckinComposer
        from cura.pulse.eldercare_pulse import ElderProfile, EldercarePulseConfig
        p = tmp_path / "pq.json"
        monkeypatch.setattr(pending, "PENDING_FILE", p)
        cfg = EldercarePulseConfig(profile=ElderProfile(
            name="Margaret Chen", preferred_name="Margaret"))
        c = CheckinComposer()
        # walk compositions until one carries the safety question
        for day in range(12):
            checkin = c.compose_evening(cfg, days_heard=day, rotation=day)
            if any(getattr(e, "category", "") == "home_safety"
                   for e in checkin.enrichments):
                _remember_question(checkin)
                assert p.exists(), "the question was asked and not remembered"
                return
        pytest.skip("no safety question surfaced in 12 compositions")

    def test_a_check_in_with_no_question_records_nothing(self, tmp_path,
                                                          monkeypatch):
        """A stale pending question would attach the next thing she says to a
        survey nobody asked."""
        from cura.comms import pending
        from cura.__main__ import _remember_question
        p = tmp_path / "pq.json"
        monkeypatch.setattr(pending, "PENDING_FILE", p)
        _remember_question(type("C", (), {"enrichments": ()})())
        assert not p.exists()

    def test_the_gaps_are_reported_when_a_responder_is_built(
            self, tmp_path, capsys):
        """A caregiver who assumes Cura has something covered when it does not
        is worse off than one who was told."""
        from cura.__main__ import _build_responder
        _build_responder(str(_wizard_config(tmp_path, dispatch=False)))
        out = capsys.readouterr().out
        assert "nobody else for Cura to call" in out, \
            "the household is never told what Cura is not handling"

    def test_a_household_with_a_dispatch_line_is_not_warned_about_one(
            self, tmp_path, capsys):
        """_outside had no writer, so this warning fired for every household
        including ones that had a dispatch line. A warning that is always true
        carries no information."""
        from cura.__main__ import _build_responder
        _build_responder(str(_wizard_config(tmp_path, dispatch=True)))
        out = capsys.readouterr().out
        assert "no monitoring service or dispatch line on file" not in out


class TestTheGraduationActuallyGraduates:
    """help_prompt graduates the press-two line through three registers over a
    fortnight — twelve distinct lines. No production caller passed days_heard,
    so it was permanently 0 and she heard the same first sentence forever.

    Built, tested, wired into both composers, and never reached: the argument
    had no source."""

    def test_days_heard_has_a_source(self, tmp_path):
        import json
        from datetime import date, timedelta
        from cura.__main__ import _days_heard
        p = tmp_path / "c.json"
        p.write_text(json.dumps({
            "started_on": (date.today() - timedelta(days=20)).isoformat()}))
        assert _days_heard(str(p)) == 20

    def test_a_missing_start_date_is_earnest_not_a_crash(self, tmp_path):
        """Earnest is the right register when we do not know."""
        import json
        p = tmp_path / "c.json"
        p.write_text(json.dumps({}))
        assert _days_heard_of(p) == 0
        p.write_text("not json")
        assert _days_heard_of(p) == 0

    def test_the_wizard_records_it(self, tmp_path, monkeypatch):
        """Drives the REAL wizard, not the test helper.

        The first version asserted against _wizard_config(), which mimics the
        wizard and had drifted from it — it would have passed or failed for
        reasons about the helper rather than about setup. A fixture that
        imitates the thing it tests is its own small instance of this."""
        import builtins, json
        from cura.setup import wizard
        monkeypatch.setattr(wizard, "STATE", tmp_path / "setup-progress.json")
        monkeypatch.setattr(wizard, "OUT_DIR", tmp_path)
        monkeypatch.setattr(builtins, "input", lambda *a, **k: "")
        wizard.save({"name": "Margaret Chen", "preferred_name": "Margaret",
                     "phone": "307-555-0134", "morning": "8am", "evening": "7pm",
                     "caregiver_name": "Ray Chen",
                     "caregiver_phone": "307-555-0199",
                     "can_answer": "no", "meds": "", "address": ""})
        wizard.run()
        out = [f for f in tmp_path.glob("*.json")
               if f.name != "setup-progress.json"][0]
        assert json.loads(out.read_text()).get("started_on"), \
            "setup records no start date, so days_heard has no source"

    def test_every_sender_passes_it(self):
        """The actual defect: the composers accepted it and nobody supplied it."""
        import ast
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent
               / "cura/__main__.py").read_text()
        calls = [c for c in ast.walk(ast.parse(src))
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                 and c.func.attr in ("compose_morning", "compose_evening")]
        assert calls, "no composer calls found"
        for c in calls:
            kw = {k.arg for k in c.keywords}
            assert "days_heard" in kw, \
                "a check-in is composed without days_heard — she hears the " \
                "first earnest line forever"

    def test_the_line_actually_changes_over_time(self):
        """The property, not the plumbing: different days, different words."""
        from cura.pulse.checkin_composer import CheckinComposer
        from cura.pulse.eldercare_pulse import ElderProfile, EldercarePulseConfig
        cfg = EldercarePulseConfig(profile=ElderProfile(
            name="Margaret Chen", preferred_name="Margaret"))
        c = CheckinComposer()
        lines = {c.compose_evening(cfg, days_heard=d, rotation=d)
                 .all_messages[-1] for d in range(30)}
        assert len(lines) > 3, f"only {len(lines)} distinct closing lines in 30 days"


def _days_heard_of(p):
    from cura.__main__ import _days_heard
    return _days_heard(str(p))
