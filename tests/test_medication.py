"""Tests for medication schedules — daily, weekly, and as-needed.

The safety property under test throughout: an unrecorded dose is
indistinguishable from no dose, so UNKNOWN must never resolve to ALLOWED.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cura.pulse.medication import (
    Medication, PRNVerdict, Schedule, due_today, needs_clarification,
    parse_medication, prn_status, slots_for,
)

NOW = datetime(2026, 9, 2, 20, 0, tzinfo=timezone.utc)   # Wed, 2pm Mountain
MT = timezone(timedelta(hours=-6))


def _p(timing: str, name: str = "X") -> Medication:
    return parse_medication({"name": name, "time": timing})


class TestDoseQuantityIsNotAClockTime:
    """FS-59d1316ced28. "1 tab at 7pm" resolved to MORNING, because the parser
    read the dose quantity as the hour — a twelve-hour error off an ordinary
    label."""

    @pytest.mark.parametrize("timing,expected", [
        ("1 tab at 7pm", "evening"),
        ("2 pills at 8am", "morning"),
        ("5mg at 9pm", "evening"),
        ("1 tablet at 8 am", "morning"),
        ("2 capsules at 10pm", "evening"),
        ("10 mg at 7:30pm", "evening"),
    ])
    def test_quantity_does_not_become_the_hour(self, timing, expected):
        assert _p(timing).slots == {expected}

    @pytest.mark.parametrize("timing,expected", [
        ("2 tablets at 8", "morning"),
        ("1 tab at 8", "morning"),
        ("3 pills at 9", "morning"),
        ("10 mg at 7", "morning"),
    ])
    def test_a_labelled_quantity_is_removed_so_the_hour_is_unambiguous(
            self, timing, expected):
        """This is what stripping dose quantities actually buys. Without it
        "2 tablets at 8" has two bare numbers and falls to silence; with it the
        quantity is identifiable and 8 is plainly the hour."""
        assert _p(timing).slots == {expected}

    def test_ambiguous_bare_numbers_resolve_to_silence(self):
        """"take 2 at 8" could be 2 tablets at 8, or 2am and 8am. Guessing is
        a dosing error; silence is recoverable."""
        assert _p("take 2 at 8").schedule is Schedule.UNKNOWN
        assert _p("take 2 at 8").slots == set()


class TestPRNIsNeverAnnounced:
    """A PRN medication is a guard, not a reminder. There is no time for it,
    and announcing one manufactures a dose nobody asked for."""

    @pytest.mark.parametrize("timing", [
        "as needed for pain", "every 4 hours as needed", "q6h prn",
        "prn", "if needed", "as needed, every 4-6 hours",
        "when she needs it", "rescue inhaler as needed",
    ])
    def test_prn_is_recognised_and_never_announceable(self, timing):
        m = _p(timing)
        assert m.schedule is Schedule.PRN
        assert m.announceable is False
        assert m.slots == set()
        assert slots_for(m, NOW) == set()
        assert due_today(m, NOW) is False

    def test_prn_with_a_number_is_not_read_as_a_clock(self):
        """"every 4 hours as needed" once resolved to 4am, announcing a rescue
        opioid at the morning check-in."""
        m = _p("every 4 hours as needed")
        assert m.schedule is Schedule.PRN
        assert m.min_interval_hours == 4.0

    def test_interval_range_takes_the_lower_bound(self):
        """"every 4-6 hours": 4 is the earliest permitted, so 4 is the guard."""
        assert _p("as needed, every 4-6 hours").min_interval_hours == 4.0

    def test_daily_maximum_is_parsed(self):
        m = _p("as needed, every 4-6 hours, no more than 4 in 24 hours")
        assert m.max_per_day == 4


class TestWeekly:
    def test_weekly_fires_only_on_its_day(self):
        m = _p("Sunday morning")
        assert m.schedule is Schedule.WEEKLY
        fired = [datetime(2026, 9, 7 + d, 9, tzinfo=timezone.utc)
                 for d in range(7) if due_today(m, datetime(2026, 9, 7 + d, 9,
                                                            tzinfo=timezone.utc))]
        assert len(fired) == 1 and fired[0].strftime("%a") == "Sun"

    @pytest.mark.parametrize("timing,days", [
        ("Thursdays", {3}), ("Sundays", {6}), ("Thursday", {3}),
        ("every Monday and Thursday at 8am", {0, 3}),
    ])
    def test_plural_and_multiple_days(self, timing, days):
        """"Thursdays" is how a person actually says it."""
        assert _p(timing).days == days

    def test_weekly_without_a_day_is_not_guessed(self):
        """Guessing the day is a dose on the wrong day, every week."""
        m = _p("weekly")
        assert m.schedule is Schedule.UNKNOWN and m.slots == set()

    def test_sunrise_is_not_sunday(self):
        assert _p("sunrise").schedule is Schedule.DAILY
        assert _p("sunrise").days == set()


class TestPRNGuard:
    """The core safety property."""

    OXY = "as needed, every 4-6 hours, no more than 4 in 24 hours"

    def test_no_record_is_unknown_not_allowed(self):
        s = prn_status(_p(self.OXY), NOW, doses=None)
        assert s.verdict is PRNVerdict.UNKNOWN
        assert s.safe_to_take is False

    def test_empty_log_without_confirmed_logging_is_unknown(self):
        """An empty list because nobody writes to it looks exactly like an
        empty list because she has taken none."""
        s = prn_status(_p(self.OXY), NOW, doses=[], ever_recorded=False)
        assert s.verdict is PRNVerdict.UNKNOWN
        assert s.safe_to_take is False

    def test_empty_log_with_confirmed_logging_is_allowed(self):
        s = prn_status(_p(self.OXY), NOW, doses=[], ever_recorded=True)
        assert s.verdict is PRNVerdict.ALLOWED

    def test_too_soon(self):
        s = prn_status(_p(self.OXY), NOW, doses=[NOW - timedelta(minutes=30)])
        assert s.verdict is PRNVerdict.TOO_SOON
        assert s.safe_to_take is False
        assert s.next_allowed == NOW - timedelta(minutes=30) + timedelta(hours=4)

    def test_allowed_after_the_interval(self):
        s = prn_status(_p(self.OXY), NOW, doses=[NOW - timedelta(hours=5)])
        assert s.verdict is PRNVerdict.ALLOWED and s.safe_to_take is True

    def test_daily_maximum_blocks_even_when_interval_has_passed(self):
        doses = [NOW - timedelta(hours=h) for h in (20, 14, 9, 5)]
        s = prn_status(_p(self.OXY), NOW, doses=doses)
        assert s.verdict is PRNVerdict.AT_DAILY_MAX
        assert s.safe_to_take is False

    def test_doses_older_than_24h_do_not_count_to_the_maximum(self):
        doses = [NOW - timedelta(hours=h) for h in (26, 14, 9, 5)]
        s = prn_status(_p(self.OXY), NOW, doses=doses)
        assert s.verdict is PRNVerdict.ALLOWED and s.doses_today == 3

    def test_no_recorded_interval_is_unknown_even_with_a_dose_log(self):
        s = prn_status(_p("as needed for pain"), NOW,
                       doses=[NOW - timedelta(hours=1)])
        assert s.verdict is PRNVerdict.UNKNOWN and s.safe_to_take is False

    def test_safe_to_take_is_true_only_for_allowed(self):
        for v in PRNVerdict:
            s = prn_status(_p(self.OXY), NOW, doses=None)
            assert s.safe_to_take is (s.verdict is PRNVerdict.ALLOWED)


class TestSpokenTimesCannotBeMisheard:
    def test_time_of_day_is_named(self):
        """"1:30" is a coin flip to someone who cannot reconstruct the day."""
        s = prn_status(_p(TestPRNGuard.OXY), NOW,
                       doses=[NOW - timedelta(minutes=30)], tz=MT)
        assert "in the afternoon" in s.reason
        assert "1:30 in the afternoon" in s.reason

    def test_times_are_spoken_in_the_household_timezone(self):
        """Without tz, Cura reads back UTC — six hours off, in the direction
        of taking the next dose too early."""
        doses = [NOW - timedelta(minutes=30)]
        local = prn_status(_p(TestPRNGuard.OXY), NOW, doses=doses, tz=MT).reason
        utc = prn_status(_p(TestPRNGuard.OXY), NOW, doses=doses).reason
        assert "1:30 in the afternoon" in local
        assert "7:30 in the evening" in utc
        assert local != utc


class TestCaregiverIsToldWhatCuraIsNotDoing:
    def test_weekly_is_not_reported_unknown_on_its_off_days(self):
        """A list that cries wolf six days a week is one a caregiver stops
        reading."""
        from cura.pulse.eldercare_pulse import unknown_timing_medications
        meds = [{"name": "Alendronate", "time": "Sunday morning"}]
        assert unknown_timing_medications(meds) == []

    def test_prn_is_not_reported_as_unhandled(self):
        from cura.pulse.eldercare_pulse import unknown_timing_medications
        meds = [{"name": "Oxycodone", "time": "as needed, every 4 hours"}]
        assert unknown_timing_medications(meds) == []

    def test_genuinely_unknown_is_reported(self):
        from cura.pulse.eldercare_pulse import unknown_timing_medications
        meds = [{"name": "Donepezil", "time": ""},
                {"name": "Warfarin", "time": "weekly"}]
        assert unknown_timing_medications(meds) == ["Donepezil", "Warfarin"]

    def test_clarifications_say_why(self):
        qs = dict(needs_clarification([
            {"name": "Alendronate", "time": "Thursdays"},
            {"name": "Oxycodone", "time": "as needed for pain"},
            {"name": "Donepezil", "time": ""},
        ]))
        assert "not what time of day" in qs["Alendronate"]
        assert "how long to wait" in qs["Oxycodone"]
        assert "don't know when" in qs["Donepezil"]


class TestFindingsFromTheOvernightShakedown:
    """Three parser defects confirmed by execution in the 2026-09-02 review."""

    def test_time_of_day_plurals_are_matched(self):
        """_DAY_RE was given a trailing s? and these were not, so "Thursday
        mornings" parsed weekly-with-no-slot and was never announced at all."""
        assert _p("Thursday mornings").slots == {"morning"}
        assert _p("Thursday mornings").days == {3}
        assert _p("mornings").slots == {"morning"}
        assert _p("evenings").slots == {"evening"}
        assert _p("nights").slots == {"evening"}

    def test_every_stated_clock_time_is_kept(self):
        """Keeping only the first silently dropped the second dose."""
        assert _p("2 tabs at 8am and 1 tab at 8pm").slots == {"morning", "evening"}
        assert _p("8am and 8pm").slots == {"morning", "evening"}

    def test_twelve_hourly_is_twice_daily_not_a_noon_dose(self):
        """"every 12 hours" handed 12 to the clock parser and came back as a
        single noon dose — half the day's medication, silently."""
        m = _p("every 12 hours")
        assert m.schedule is Schedule.DAILY
        assert m.slots == {"morning", "evening"}

    def test_a_regimen_with_more_doses_than_slots_is_refused_not_truncated(self):
        """Three doses a day cannot be expressed in two check-ins. Announcing
        the two that fit would present a partial schedule as a complete one."""
        m = _p("every 8 hours")
        assert m.schedule is Schedule.UNKNOWN
        assert m.slots == set()
        why = dict(needs_clarification([{"name": "Amoxicillin",
                                         "time": "every 8 hours"}]))
        assert "more doses" in why["Amoxicillin"]

    def test_once_daily_still_asks_what_time(self):
        m = _p("every 24 hours")
        assert m.schedule is Schedule.UNKNOWN
        why = dict(needs_clarification([{"name": "D", "time": "every 24 hours"}]))
        assert "what time of day" in why["D"]

    def test_prn_intervals_are_still_prn_not_daily(self):
        """The interval branch must not capture as-needed drugs."""
        m = _p("every 4 hours as needed")
        assert m.schedule is Schedule.PRN and m.announceable is False
