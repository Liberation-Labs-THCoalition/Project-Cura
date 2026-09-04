"""The escalation ladder.

Escalation was one attempt at the contacts; if nobody answered it logged a line
and stopped. For this household that is the LIKELIEST bad outcome, not an edge
case: the sole caregiver is the only reachable person, so if HE falls, Cura's
only contact is the person who is down.
"""
from __future__ import annotations

import pytest

from cura.comms.ladder import LADDER, Rung, climb
from cura.household import Household, Member, Reach


def _dialer(answers=()):
    """Returns (fn, log). `answers` = numbers that pick up."""
    log = []
    def fn(number, message):
        log.append(number)
        return number in answers
    return fn, log


def _house(**overrides):
    people = {
        "margaret": Member("margaret", "Margaret Chen", "Margaret",
                           "+13075550134", Reach.NEVER),
        "ray": Member("ray", "Ray Chen", "Ray", "+13075550199",
                      Reach.SCHEDULED, cares_for=("margaret",)),
    }
    people.update(overrides)
    return Household(people)


THOMAS = Member("thomas", "Thomas", "Thomas", "+15305551234",
                Reach.ON_REQUEST, cares_for=("ray", "margaret"))


class TestTheLadderIsBounded:
    def test_every_rung_attempted_is_on_the_declared_list(self):
        """An escalation that improvises until it 'succeeds' is the thing that
        does something unforgivable at 3am."""
        sms, _ = _dialer()
        call, _ = _dialer()
        t = climb(_house(thomas=THOMAS), "ray", "ctx",
                  send_sms=sms, place_call=call)
        assert [r.rung for r in t.rungs] == list(LADDER)

    def test_it_stops_at_the_first_answered_call(self):
        sms, _ = _dialer(answers=("+15305551234",))
        call, log = _dialer(answers=("+15305551234",))
        t = climb(_house(thomas=THOMAS), "ray", "ctx",
                  send_sms=sms, place_call=call)
        assert t.reached_anyone
        later = [r for r in t.rungs if not r.attempted
                 and "already reached" in r.unavailable_because]
        assert later, "rungs below the success were not marked unattempted"


class TestADeliveredTextIsNotAPerson:
    """The false success this module exists to prevent — and which its first
    implementation shipped, fifteen minutes after a comment warning about it."""

    def test_sms_delivery_alone_is_not_reaching_anyone(self):
        sms, _ = _dialer(answers=("+15305551234",))     # text delivers
        call, _ = _dialer(answers=())                    # nobody picks up
        t = climb(_house(thomas=THOMAS), "ray", "ctx",
                  send_sms=sms, place_call=call)
        assert t.reached_anyone is False
        assert "NOBODY WAS REACHED" in t.summary()

    def test_the_delivered_text_is_still_reported(self):
        """It may be the thing that actually wakes someone. Record it."""
        sms, _ = _dialer(answers=("+15305551234",))
        call, _ = _dialer(answers=())
        t = climb(_house(thomas=THOMAS), "ray", "ctx",
                  send_sms=sms, place_call=call)
        assert "text" in t.summary() and "Thomas" in t.summary()

    def test_an_answered_call_does_count(self):
        sms, _ = _dialer()
        call, _ = _dialer(answers=("+15305551234",))
        t = climb(_house(thomas=THOMAS), "ray", "ctx",
                  send_sms=sms, place_call=call)
        assert t.reached_anyone and "Reached Thomas" in t.summary()


class TestARungThatNeverExistedIsNotARungThatFailed:
    """Collapsing the two produces a trail reading like six attempts when there
    were two — which is how a family concludes everything possible was tried."""

    def test_the_sole_caregiver_scenario_reports_zero_attempts(self):
        sms, stexts = _dialer()
        call, clog = _dialer()
        t = climb(_house(), "ray", "no movement since 6am",
                  send_sms=sms, place_call=call)
        assert t.reached_anyone is False
        assert t.rungs_attempted == 0
        assert t.rungs_unavailable == len(LADDER)
        assert "never existed to try" in t.summary()
        assert clog == [] and stexts == []

    def test_attempted_and_unavailable_are_counted_separately(self):
        sms, _ = _dialer()
        call, _ = _dialer()
        t = climb(_house(thomas=THOMAS), "ray", "ctx",
                  send_sms=sms, place_call=call)
        assert t.rungs_attempted + t.rungs_unavailable == len(LADDER)
        assert t.rungs_attempted > 0 and t.rungs_unavailable > 0

    def test_the_outside_rung_says_why_it_matters_when_empty(self):
        sms, _ = _dialer()
        call, _ = _dialer()
        t = climb(_house(), "ray", "ctx", send_sms=sms, place_call=call)
        outside = next(r for r in t.rungs if r.rung is Rung.CALL_OUTSIDE)
        assert not outside.attempted
        assert "caregiver is the one in trouble" in outside.unavailable_because


class TestNobodyIsCalledAboutTheirOwnEmergency:
    def test_the_subject_is_never_contacted(self):
        sms, texts = _dialer()
        call, calls = _dialer()
        climb(_house(thomas=THOMAS), "margaret", "fall detected",
              send_sms=sms, place_call=call)
        assert "+13075550134" not in texts + calls

    def test_the_person_who_raised_the_alarm_is_not_called_back(self):
        """Ringing the phone already on the line wastes the rung — and if they
        share a landline, rings the room the emergency is in."""
        sms, texts = _dialer()
        call, calls = _dialer()
        climb(_house(thomas=THOMAS), "margaret", "Ray called",
              send_sms=sms, place_call=call, raised_by="ray")
        assert "+13075550199" not in calls

    def test_a_never_reach_person_is_never_dialled(self):
        sms, texts = _dialer()
        call, calls = _dialer()
        climb(_house(thomas=THOMAS), "ray", "ctx", send_sms=sms, place_call=call)
        assert "+13075550134" not in texts + calls, \
            "dialled someone recorded as never-to-call"


class TestOneBadNumberDoesNotStopTheRest:
    def test_an_sms_that_raises_does_not_abort_the_broadcast(self):
        sent = []
        def sms(number, message):
            sent.append(number)
            if number == "+13075550199":
                raise RuntimeError("carrier rejected")
            return True
        call, _ = _dialer()
        t = climb(_house(thomas=THOMAS), "margaret", "ctx",
                  send_sms=sms, place_call=call)
        assert "+15305551234" in sent, "one bad number stopped the broadcast"

    def test_a_call_that_raises_moves_to_the_next_person(self):
        def call(number, message):
            if number == "+13075550199":
                raise RuntimeError("twilio down")
            return True
        sms, _ = _dialer()
        t = climb(_house(thomas=THOMAS), "margaret", "ctx",
                  send_sms=sms, place_call=call)
        assert t.reached_anyone


class TestExtraRungs:
    def test_the_physician_is_tried_when_the_household_cannot_be_reached(self):
        sms, _ = _dialer()
        call, log = _dialer(answers=("+13075550111",))
        t = climb(_house(thomas=THOMAS), "ray", "ctx", send_sms=sms,
                  place_call=call, physician={"name": "Dr Ruiz",
                                              "phone": "+13075550111"})
        assert "+13075550111" in log and t.reached_anyone

    def test_no_physician_on_file_is_unavailable_not_failed(self):
        sms, _ = _dialer()
        call, _ = _dialer()
        t = climb(_house(), "ray", "ctx", send_sms=sms, place_call=call)
        doc = next(r for r in t.rungs if r.rung is Rung.CALL_PHYSICIAN)
        assert doc.attempted is False and doc.failed == []


class TestTheLadderIsActuallyWired:
    """cura/comms/ladder.py was written, tested and committed with no caller.
    That is the defect this codebase produces more than any other, and it was
    about to happen in the module built to make sure somebody gets reached."""

    class _Voice:
        def __init__(self, answers=(), sms_ok=True):
            self.answers, self.sms_ok = set(answers), sms_ok
            self.calls, self.texts = [], []
        async def send_sms(self, to_number, message):
            self.texts.append(to_number)
            return type("S", (), {"sent": self.sms_ok, "sid": "SM1"})()
        async def call(self, to_number, messages=None, **kw):
            self.calls.append(to_number)
            return type("C", (), {"answered": to_number in self.answers})()

    def test_build_ladder_escalation_climbs_and_reaches(self):
        from cura.comms.escalation import build_ladder_escalation
        v = self._Voice(answers=("+15305551234",))
        cb = build_ladder_escalation(v, _house(thomas=THOMAS), "ray")
        assert cb is not None
        cb("Ray pressed 2")
        assert "+15305551234" in v.calls
        assert "+13075550134" not in v.calls + v.texts, "dialled a NEVER member"

    def test_it_refuses_when_nobody_can_be_reached(self):
        """None is a refusal, not a degraded mode."""
        from cura.comms.escalation import build_ladder_escalation
        empty = Household({"margaret": Member(
            "margaret", "Margaret Chen", "Margaret", "+13075550134", Reach.NEVER)})
        assert build_ladder_escalation(self._Voice(), empty, "margaret") is None

    def test_an_unanswered_climb_does_not_report_success(self, caplog):
        import logging
        from cura.comms.escalation import build_ladder_escalation
        v = self._Voice(answers=())      # texts deliver, nobody answers
        cb = build_ladder_escalation(v, _house(thomas=THOMAS), "ray")
        with caplog.at_level(logging.CRITICAL):
            cb("no movement since 6am")
        assert any("NOBODY WAS REACHED" in r.message for r in caplog.records), \
            "an unanswered escalation did not log CRITICAL"

    def test_the_outcome_is_always_awaited(self):
        """The old escalation used loop.create_task and set results=None when a
        loop was already running, so in that path it never learned whether
        anyone was reached — the 'nobody answered' branch could not fire."""
        import asyncio
        from cura.comms.escalation import build_ladder_escalation
        v = self._Voice(answers=("+15305551234",))
        cb = build_ladder_escalation(v, _house(thomas=THOMAS), "ray")
        async def inside_a_loop():
            cb("from async context")
        asyncio.run(inside_a_loop())
        assert v.calls, "escalation placed no call from inside a running loop"
