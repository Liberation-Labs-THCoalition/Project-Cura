"""Turning what the caregiver says into a dose time, or refusing to.

The dose ledger answered correctly and NOTHING called record() — the same shape
prn_status was in, in the module written to fix it.

Refusing is the feature. A wrong dose time recorded too late permits a double
dose; too early it withholds a painkiller from someone in pain.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cura.pulse.dose_answer import parse_dose_time, record_dose_answer
from cura.pulse.dose_ledger import DoseLedger, prn_answer
from cura.pulse.medication import PRNVerdict

NOW = datetime(2026, 9, 4, 20, 0, tzinfo=timezone.utc)
OXY = {"name": "oxycodone",
       "time": "as needed, every 4-6 hours, no more than 4 in 24 hours"}


class TestItRefusesWhatItCannotPin:
    @pytest.mark.parametrize("said", [
        "after lunch", "this morning", "before bed", "a while ago",
        "earlier", "teatime", "a few hours",
    ])
    def test_a_vague_window_is_refused_and_says_why(self, said):
        """"After lunch" spans three hours. For a four-hourly opioid that is
        the whole interval.

        Asserts the SPECIFIC reason, not just that it refused. My first version
        checked only `when is None and why`, and deleting the vague-phrase list
        entirely still passed — these phrases fall through to a generic refusal
        anyway, so the list changes only the wording. But Cura says that wording
        aloud, and "after lunch could be a three-hour window" teaches him what
        to say next time where "no time was given" does not. A test that cannot
        tell the two apart is not testing the thing that matters."""
        when, why = parse_dose_time(said, NOW)
        assert when is None
        assert "window" in why or "interval" in why, \
            f"refused {said!r} with a generic reason: {why!r}"
        assert said in why, "the refusal does not repeat what he actually said"

    @pytest.mark.parametrize("said", ["about two", "two", "at four", "10"])
    def test_an_hour_with_no_meridiem_is_refused(self, said):
        """Guessing picks a twelve-hour error — the same class that made
        "1 tab at 7pm" resolve to morning."""
        assert parse_dose_time(said, NOW)[0] is None

    @pytest.mark.parametrize("said", [
        "I don't know", "can't remember", "no idea", "not sure",
    ])
    def test_not_remembering_is_refused_not_guessed(self, said):
        assert parse_dose_time(said, NOW)[0] is None

    def test_no_dose_is_distinguished_from_no_answer(self):
        when, why = parse_dose_time("she didn't need any", NOW)
        assert when is None and why == "no dose was given"

    def test_the_refusal_says_why(self):
        """A caregiver who answered and heard nothing will assume it landed."""
        assert parse_dose_time("after lunch", NOW)[1]


class TestItAcceptsWhatIsActuallySpecific:
    @pytest.mark.parametrize("said,hour", [
        ("2pm", 14), ("about 2pm", 14), ("at 14:30", 14), ("10pm", 22),
        ("two in the afternoon", 14), ("eight in the morning", 8),
        ("eleven at night", 23), ("at ten last night", 22),
    ])
    def test_clear_times_parse(self, said, hour):
        """A caregiver says "two in the afternoon", not "14:00". A digits-only
        parser refuses the clearest answers he is likely to give."""
        when, why = parse_dose_time(said, NOW)
        assert when is not None, f"{said!r} refused: {why}"
        assert when.hour == hour

    def test_half_past(self):
        when, _ = parse_dose_time("half past two in the afternoon", NOW)
        assert when.hour == 14 and when.minute == 30

    @pytest.mark.parametrize("said,delta", [
        ("three hours ago", timedelta(hours=3)),
        ("half an hour ago", timedelta(minutes=30)),
        ("20 minutes ago", timedelta(minutes=20)),
        ("an hour ago", timedelta(hours=1)),
    ])
    def test_relative_times_parse(self, said, delta):
        when, _ = parse_dose_time(said, NOW)
        assert when == NOW - delta

    def test_a_time_later_than_now_is_yesterday(self):
        """"At ten" said at nine in the morning means last night."""
        morning = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)
        when, _ = parse_dose_time("10pm", morning)
        assert when < morning


class TestTheJoin:
    """The ledger answered correctly and nothing supplied it."""

    def test_an_answer_changes_what_the_guard_says(self):
        led = DoseLedger()
        assert prn_answer(OXY, led, NOW).verdict is PRNVerdict.UNKNOWN
        ok, _ = record_dose_answer("two in the afternoon", "oxycodone", led, NOW)
        assert ok
        assert prn_answer(OXY, led, NOW).verdict is not PRNVerdict.UNKNOWN

    def test_a_recent_dose_makes_the_guard_say_too_soon(self):
        led = DoseLedger()
        record_dose_answer("half an hour ago", "oxycodone", led, NOW)
        assert prn_answer(OXY, led, NOW).verdict is PRNVerdict.TOO_SOON

    def test_a_refused_answer_records_nothing(self):
        led = DoseLedger()
        ok, _ = record_dose_answer("after lunch", "oxycodone", led, NOW)
        assert ok is False
        assert led.ever_recorded is False
        assert prn_answer(OXY, led, NOW).verdict is PRNVerdict.UNKNOWN

    def test_the_caregiver_is_an_authoritative_source(self):
        from cura.pulse.dose_ledger import Source
        led = DoseLedger()
        record_dose_answer("2pm", "oxycodone", led, NOW)
        assert led.doses[0].source == Source.CAREGIVER
        assert led.ever_recorded is True

    def test_cura_always_says_something_back(self):
        for said in ["2pm", "after lunch", "she didn't need any", "I don't know"]:
            _, reply = record_dose_answer(said, "oxycodone", DoseLedger(), NOW)
            assert reply.strip(), f"{said!r} produced silence"

    def test_what_he_said_is_kept_verbatim(self):
        led = DoseLedger()
        record_dose_answer("about 2pm, after her nap", "oxycodone", led, NOW)
        assert "after her nap" in led.doses[0].note


class TestTheCheckInAsks:
    def test_a_prn_medication_produces_a_question(self):
        from cura.household import Household, Member, Reach
        from cura.pulse.caregiver_checkin import compose_caregiver_checkin
        h = Household({
            "margaret": Member("margaret", "Margaret Chen", "Margaret",
                               "+13075550134", Reach.NEVER),
            "ray": Member("ray", "Ray Chen", "Ray", "+13075550199",
                          Reach.SCHEDULED, cares_for=("margaret",))})
        lines = compose_caregiver_checkin(
            h, "ray", prn_to_ask=["oxycodone"]).lines
        asked = [l for l in lines if "oxycodone" in l]
        assert asked, "the check-in never asks about the as-needed medicine"
        assert "last have" in asked[0]
        assert "Roughly is fine" in asked[0]


class TestItNeverAssumesANumber:
    """The first version defaulted a missing number to 1, so "three hours ago"
    — where "three" was not in the alternatives and did not match — was
    silently recorded as ONE hour ago. A two-hour error toward TOO_SOON, which
    withholds a painkiller from someone in pain. A silent wrong answer,
    produced by the module written to refuse exactly those."""

    @pytest.mark.parametrize("said,hours", [
        ("three hours ago", 3), ("seven hours ago", 7),
        ("a couple of hours ago", 2), ("1.5 hours ago", 1.5),
    ])
    def test_spelled_numbers_are_read_not_defaulted(self, said, hours):
        when, why = parse_dose_time(said, NOW)
        assert when is not None, f"{said!r} refused: {why}"
        assert when == NOW - timedelta(hours=hours)

    def test_a_missing_number_is_refused_not_assumed(self):
        when, why = parse_dose_time("hours ago", NOW)
        assert when is None
        assert "will not assume" in why

    def test_no_relative_answer_silently_becomes_one_hour(self):
        """The property, over the whole space: if it parses, it parses to what
        was said — never to a default."""
        for n, word in ((2, "two"), (3, "three"), (4, "four"), (5, "five"),
                        (6, "six"), (8, "eight"), (12, "twelve")):
            when, _ = parse_dose_time(f"{word} hours ago", NOW)
            assert when == NOW - timedelta(hours=n), \
                f"{word!r} did not parse to {n} hours"
