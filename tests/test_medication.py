"""Tests for medication schedules — daily, weekly, and as-needed.

The safety property under test throughout: an unrecorded dose is
indistinguishable from no dose, so UNKNOWN must never resolve to ALLOWED.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import permutations

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

    def test_interval_is_measured_from_the_latest_dose_not_the_earliest(self):
        """Mutation ``last = doses[-1]`` -> ``last = doses[0]`` survived the
        suite: every interval test used a single dose, or a log whose earliest
        dose also cleared the interval. With doses five hours and one hour ago
        and a four-hour minimum, the mutant measured from the five-hour-old
        dose and answered ALLOWED — approving an oxycodone double dose one
        hour after the last one, for a woman who cannot remember taking it.
        The log is passed out of order on purpose: the guard must find the
        latest dose wherever it sits in the list, and the wait it quotes must
        be counted from that dose, not merely happen to say TOO_SOON.
        """
        latest = NOW - timedelta(hours=1)
        s = prn_status(_p(self.OXY), NOW,
                       doses=[latest, NOW - timedelta(hours=5)])
        assert s.verdict is PRNVerdict.TOO_SOON
        assert s.safe_to_take is False
        assert s.next_allowed == latest + timedelta(hours=4)
        assert s.doses_today == 2

    def test_the_guard_is_indifferent_to_the_order_the_log_arrived_in(self):
        """Mutation ``doses = sorted(doses or [])`` -> ``list(doses or [])``
        survived the suite: every multi-dose fixture arrived already sorted
        ascending, so the sort never did observable work. Without it the
        guard measures the interval from whichever entry happens to sit last
        IN THE LIST -- and a real dose log is not sorted: caregiver entries
        merge with phone-logged ones, and a backdated correction lands at the
        end. The mutant would have said ALLOWED sixty minutes after the real
        latest oxycodone dose, to a household where nobody can catch it.

        The property: verdict, quoted wait, and dose count depend only on
        the SET of doses, never on the order they were written down.
        """
        latest = NOW - timedelta(hours=1)
        log = [latest, NOW - timedelta(hours=5), NOW - timedelta(hours=9)]
        for ordering in permutations(log):
            s = prn_status(_p(self.OXY), NOW, doses=list(ordering))
            assert s.verdict is PRNVerdict.TOO_SOON, list(ordering)
            assert s.safe_to_take is False
            assert s.next_allowed == latest + timedelta(hours=4)
            assert s.doses_today == 3

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

    @pytest.mark.parametrize("minutes_ago,tz,local_next,utc_next", [
        # Dose 1:30pm MT: next allowed 5:30pm MT; UTC would say 11:30 at night.
        (30, MT, "5:30 in the evening", "11:30 at night"),
        # Dose noon MT: next allowed 4:00pm MT; UTC would say 10:00 at night.
        (120, MT, "4:00 in the afternoon", "10:00 at night"),
        # One zone further west: the property, not the Wyoming instance.
        (30, timezone(timedelta(hours=-7)), "4:30 in the afternoon",
         "11:30 at night"),
    ])
    def test_next_allowed_time_is_spoken_in_the_household_timezone(
            self, minutes_ago, tz, local_next, utc_next):
        """Mutation (2026-09): the second _spoken_time call site dropped tz --
        ``so around {_spoken_time(nxt)}`` -- and the whole suite stayed green,
        because the tests above pin only the LAST-dose time. The guard then
        said "you had one at 1:30 in the afternoon... another would be
        alright in about 3 hours and 30 minutes, so around 11:30 at night" --
        the next-allowed time in UTC, six hours off for Wyoming, contradicting
        the correct wait quoted in the same sentence. A man with failing
        eyesight who lives by the spoken word either withholds his wife's pain
        relief for hours or learns the guard cannot do arithmetic.

        The property: EVERY clock time in a TOO_SOON reason is household-local.
        So the next-allowed time must appear in local terms and its UTC
        rendering must not appear at all, at several dose times and at more
        than one offset, chosen so the two renderings always differ.
        """
        s = prn_status(_p(TestPRNGuard.OXY), NOW,
                       doses=[NOW - timedelta(minutes=minutes_ago)], tz=tz)
        assert s.verdict is PRNVerdict.TOO_SOON
        assert local_next in s.reason
        assert utc_next not in s.reason


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


class TestDayKnownTimeUnknownIsStillReported:
    """Closes a mutation that survived the suite (eldercare_pulse.py:92).

    MUTATION: unknown_timing_medications dropped its WEEKLY-without-slots
    clause --

        if parsed.schedule is Schedule.UNKNOWN or (
                parsed.schedule is Schedule.WEEKLY and not parsed.slots):

    became

        if parsed.schedule is Schedule.UNKNOWN:

    WHAT THE HOUSEHOLD WOULD HAVE EXPERIENCED: "Alendronate on Thursdays"
    parses WEEKLY with a day but no time of day, so it is never announced at
    any check-in -- which is correct, no slot is known -- but under the mutant
    it ALSO vanished from the caregiver's not-handled list. He assumes Cura is
    reminding her; the weekly bisphosphonate is silently missed every single
    week. Silent omission is safe for dosing ONLY because this list exists; a
    medication that is both unannounced and unlisted is the exact false
    all-clear the list was built to prevent.

    Property, not instance: EVERY phrasing that yields a known day with an
    unknown time of day must appear in the list, precisely because the same
    parse guarantees the medication will never be spoken. The suite already
    covered the UNKNOWN inputs ('', 'weekly') and the slot-bearing weekly
    ('Sunday morning', excluded) -- the day-without-time shape between them
    was tested only through needs_clarification, a different function.
    """

    DAY_ONLY = [
        {"name": "Alendronate", "time": "Thursdays"},
        {"name": "Methotrexate", "time": "on Sundays"},
        {"name": "B12", "time": "every Tuesday"},
    ]

    @pytest.mark.parametrize("med", DAY_ONLY, ids=lambda m: m["time"])
    def test_weekly_day_without_time_is_listed_as_not_handled(self, med):
        from cura.pulse.eldercare_pulse import unknown_timing_medications
        parsed = parse_medication(med)
        # Precondition: this really is the day-without-time shape the WEEKLY
        # clause exists for -- WEEKLY, not UNKNOWN (the mutant keeps UNKNOWN).
        assert parsed.schedule is Schedule.WEEKLY
        assert not parsed.slots
        # It is never announced: no slot on any day of the week...
        week = [datetime(2026, 9, 7 + d, 8, 0) for d in range(7)]  # Mon..Sun
        assert all(slots_for(parsed, day) == set() for day in week)
        # ...so absence from the not-handled list is a false all-clear.
        assert unknown_timing_medications([med]) == [med["name"]], (
            f"{med['name']} ({med['time']!r}) is never announced, and the "
            f"caregiver was never told Cura is not handling it")

    def test_the_whole_cabinet_reports_every_unhandled_medication(self):
        """The list must carry every unhandled medication at once: day-only
        weeklies alongside the genuinely UNKNOWN, with handled drugs absent."""
        from cura.pulse.eldercare_pulse import unknown_timing_medications
        cabinet = [
            {"name": "Lisinopril", "time": "8am"},                 # handled
            {"name": "Alendronate", "time": "Thursdays"},          # day, no time
            {"name": "Donepezil", "time": ""},                     # unknown
            {"name": "Oxycodone", "time": "as needed for pain"},   # PRN guard
            {"name": "Methotrexate", "time": "Sunday morning"},    # handled
        ]
        assert unknown_timing_medications(cabinet) == ["Alendronate", "Donepezil"]


class TestNoonBelongsToTheEveningCheckIn:
    """Closes a mutation that survived the suite (medication.py:280).

    MUTATION: the hour-to-slot mapping

        slots = {"morning" if h < 12 else "evening" for h in hours}

    became

        slots = {"morning" if h <= 12 else "evening" for h in hours}

    WHAT THE HOUSEHOLD WOULD HAVE EXPERIENCED: a '12pm' medication was
    announced at the 8am morning check-in instead of the evening one -- a
    confident wrong-time prompt, four hours early, to a woman who will
    believe it and may take it again when the pill organizer says noon.

    WHY NOTHING CAUGHT IT: no test anywhere used a noon time. Every
    parametrized clock hour was 7-10 am/pm or 18:00, so the 12 o'clock
    boundary of the slot mapping was completely unpinned.

    Property, not instance: the morning slot is the hours STRICTLY before
    noon. Hour 12 ('12pm', however written) is the first hour of the
    afternoon and belongs to the evening check-in; 11:59am is the last
    minute of the morning. Midnight ('12am') resolves to hour 0 and stays
    morning, pinning the other half of the 12-o'clock conversion.

    NOTE for the next person: these timings deliberately write the meridiem
    with no space ('12pm', not '12 pm'). With a space, \\bpm\\b matches
    _EVENING_WORDS and the word path supplies the slot before the
    hour-to-slot mapping ever runs -- a '12 pm' test would keep passing
    under this very mutation, which is how a check stops being able to fail.
    """

    @pytest.mark.parametrize("timing,expected", [
        ("12pm", {"evening"}),          # noon exactly: the mutated boundary
        ("12:00pm", {"evening"}),
        ("12:30pm", {"evening"}),       # lunchtime, as a label writes it
        ("11am", {"morning"}),          # last whole hour of the morning
        ("11:59am", {"morning"}),       # last minute of the morning
        ("12am", {"morning"}),          # midnight -> hour 0 -> morning
    ])
    def test_noon_is_the_first_hour_of_the_evening_slot(self, timing, expected):
        m = _p(timing)
        assert m.schedule is Schedule.DAILY
        assert m.slots == expected, (
            f"{timing!r} parsed to slots {m.slots}; a noon medication in the "
            f"morning slot is announced four hours early")

    def test_a_noon_dose_is_not_folded_into_a_morning_dose(self):
        """Two doses spanning noon must fill BOTH slots. Under the mutant,
        '8am and 12pm' collapsed to {'morning'} -- the noon dose silently
        joined the 8am announcement and the evening check-in never named it."""
        m = _p("8am and 12pm")
        assert m.schedule is Schedule.DAILY
        assert m.slots == {"morning", "evening"}
