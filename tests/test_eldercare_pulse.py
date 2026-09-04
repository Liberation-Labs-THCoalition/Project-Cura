"""Tests for eldercare pulse — the heartbeat of Cura."""
from __future__ import annotations

from datetime import datetime, timezone

from cura.pulse.eldercare_pulse import (
    ElderProfile,
    EldercarePulseConfig,
    CheckInResult,
    HealthObservation,
)


def _make_profile(**kwargs) -> ElderProfile:
    defaults = dict(
        name="Margaret Chen",
        preferred_name="Margaret",
        phone="+15551234567",
        medications=[
            {"name": "Lisinopril", "time": "morning"},
            {"name": "Metformin", "time": "morning"},
            {"name": "Amlodipine", "time": "evening"},
        ],
        emergency_contacts=[
            {"name": "Sarah Chen", "phone": "+15559876543", "relation": "daughter"},
        ],
        primary_caregiver={"name": "Sarah Chen", "phone": "+15559876543"},
        address="123 Elm Street, Springfield, IL",
    )
    defaults.update(kwargs)
    return ElderProfile(**defaults)


class TestElderProfile:
    def test_display_name_preferred(self):
        p = _make_profile(preferred_name="Mom")
        assert p.display_name == "Mom"

    def test_display_name_fallback(self):
        p = _make_profile(preferred_name="")
        assert p.display_name == "Margaret Chen"


class TestEldercarePulseConfig:
    def test_morning_greeting(self):
        config = EldercarePulseConfig(_make_profile())
        greeting = config.generate_morning_greeting()
        assert "Margaret" in greeting

    def test_medication_reminder(self):
        config = EldercarePulseConfig(_make_profile())
        reminder = config.generate_medication_reminder()
        assert "Lisinopril" in reminder
        assert "Metformin" in reminder

    def test_medication_reminder_empty(self):
        config = EldercarePulseConfig(_make_profile(medications=[]))
        reminder = config.generate_medication_reminder()
        assert reminder == ""

    def test_evening_summary(self):
        config = EldercarePulseConfig(_make_profile())
        summary = config.generate_evening_summary()
        assert "Margaret" in summary
        assert "bed" in summary.lower()

    def test_record_checkin(self):
        config = EldercarePulseConfig(_make_profile())
        result = CheckInResult(
            timestamp=datetime.now(timezone.utc),
            check_type="morning",
            reached=True,
            response="Feeling good",
            medication_confirmed=True,
        )
        config.record_checkin(result)
        assert len(config.check_in_history) == 1
        assert config.missed_checkins_this_week == 0

    def test_missed_checkin_tracking(self):
        config = EldercarePulseConfig(_make_profile())
        for _ in range(3):
            config.record_checkin(CheckInResult(
                timestamp=datetime.now(timezone.utc),
                check_type="morning",
                reached=False,
                response="",
            ))
        assert config.missed_checkins_this_week == 3
        assert config.needs_elevated_monitoring

    def test_adherence_rate(self):
        config = EldercarePulseConfig(_make_profile())
        for confirmed in [True, True, False, True]:
            config.record_checkin(CheckInResult(
                timestamp=datetime.now(timezone.utc),
                check_type="morning",
                reached=True,
                response="ok",
                medication_confirmed=confirmed,
            ))
        assert config.adherence_rate_7d == 0.75

    def test_social_outreach_trigger(self):
        config = EldercarePulseConfig(_make_profile())
        config.days_since_outing = 4
        assert not config.needs_social_outreach
        config.days_since_outing = 5
        assert config.needs_social_outreach

    def test_crisis_level_fall(self):
        config = EldercarePulseConfig(_make_profile())
        obs = HealthObservation(
            timestamp=datetime.now(timezone.utc),
            source="accelerometer",
            observation_type="fall",
            severity=0.9,
        )
        assert config.assess_crisis_level(obs) == "crisis"

    def test_crisis_level_mild(self):
        config = EldercarePulseConfig(_make_profile())
        obs = HealthObservation(
            timestamp=datetime.now(timezone.utc),
            source="interaction",
            observation_type="gait_change",
            severity=0.2,
        )
        assert config.assess_crisis_level(obs) == "monitor"

    def test_crisis_level_alert_caregiver(self):
        config = EldercarePulseConfig(_make_profile())
        obs = HealthObservation(
            timestamp=datetime.now(timezone.utc),
            source="voice_analysis",
            observation_type="voice_change",
            severity=0.6,
        )
        assert config.assess_crisis_level(obs) == "alert_caregiver"


class TestMedicationSlots:
    """A medication must be named at the check-in it is recorded for, and at
    no other. A wrongly-timed reminder to someone with dementia is a second
    dose, not a wording slip."""

    def test_morning_medication_not_named_in_the_evening(self):
        config = EldercarePulseConfig(
            _make_profile(medications=[{"name": "Donepezil", "time": "morning"}])
        )
        assert "Donepezil" in config.generate_medication_reminder("morning")
        assert config.generate_medication_reminder("evening") == ""
        assert "Donepezil" not in config.generate_evening_summary()

    def test_evening_medication_not_named_in_the_morning(self):
        config = EldercarePulseConfig(
            _make_profile(medications=[{"name": "Amlodipine", "time": "evening"}])
        )
        assert config.generate_medication_reminder("morning") == ""
        assert "Amlodipine" in config.generate_medication_reminder("evening")
        assert "Amlodipine" in config.generate_evening_summary()

    def test_default_profile_splits_by_slot(self):
        config = EldercarePulseConfig(_make_profile())
        morning = config.generate_medication_reminder("morning")
        evening = config.generate_medication_reminder("evening")
        assert "Lisinopril" in morning and "Metformin" in morning
        assert "Amlodipine" not in morning
        assert evening == "It's time for your Amlodipine."

    def test_twice_daily_is_named_at_both(self):
        config = EldercarePulseConfig(
            _make_profile(medications=[{"name": "Metformin", "time": "twice daily"}])
        )
        assert "Metformin" in config.generate_medication_reminder("morning")
        assert "Metformin" in config.generate_medication_reminder("evening")

    def test_clock_times_resolve_to_a_slot(self):
        config = EldercarePulseConfig(
            _make_profile(medications=[
                {"name": "Levothyroxine", "time": "7am"},
                {"name": "Simvastatin", "time": "9pm"},
                {"name": "Warfarin", "time": "18:00"},
            ])
        )
        morning = config.generate_medication_reminder("morning")
        evening = config.generate_medication_reminder("evening")
        assert "Levothyroxine" in morning
        assert "Simvastatin" not in morning and "Warfarin" not in morning
        assert "Simvastatin" in evening and "Warfarin" in evening

    def test_unknown_time_is_never_announced(self):
        """Unknown timing produces silence, not a guess.

        This replaces an earlier rule that defaulted the unknown case to the
        morning check-in, on the reasoning that a missed reminder beats a
        doubled one. Sound, but it misses a case: a drug actually taken at
        night, recorded with no time, would be announced at 9am. That is not a
        missed reminder — it is a prompt at the wrong time, carrying the same
        double-dose risk the default existed to prevent.

        Silence is recoverable; the caregiver still gives the medication.
        A confident prompt at the wrong hour, to someone who cannot remember
        whether they already took it, is not.
        """
        for value in ({"name": "Aspirin"}, {"name": "Aspirin", "time": ""},
                      {"name": "Aspirin", "time": "as needed"}):
            config = EldercarePulseConfig(_make_profile(medications=[value]))
            slots = [
                s for s in ("morning", "evening")
                if "Aspirin" in config.generate_medication_reminder(s)
            ]
            assert slots == [], value

    def test_unknown_timing_is_surfaced_not_just_omitted(self):
        """Silence must be visible. If Cura is not reminding about a drug, the
        caregiver has to be told, or he will assume that it is."""
        from cura.pulse.eldercare_pulse import unknown_timing_medications
        meds = [{"name": "Donepezil", "time": ""},
                {"name": "Lisinopril", "time": "morning"}]
        assert unknown_timing_medications(meds) == ["Donepezil"]

    def test_no_medication_is_silently_dropped(self):
        meds = [{"name": f"Drug{i}", "time": "morning"} for i in range(5)]
        config = EldercarePulseConfig(_make_profile(medications=meds))
        reminder = config.generate_medication_reminder("morning")
        for m in meds:
            assert m["name"] in reminder


class TestNameIsNotDoubled:
    """The greeting says the name. Nothing that follows it may say it again
    back to back — that is the point a companion stops sounding like a person."""

    def test_medication_reminder_does_not_open_with_the_name(self):
        config = EldercarePulseConfig(_make_profile())
        assert not config.generate_medication_reminder("morning").startswith("Margaret")

    def test_evening_summary_says_the_name_once(self):
        config = EldercarePulseConfig(
            _make_profile(medications=[{"name": "Amlodipine", "time": "evening"}])
        )
        summary = config.generate_evening_summary()
        assert summary.count("Margaret") == 1, summary
        assert "Margaret. Margaret," not in summary


class TestAdherenceCountsBothMedicationSlots:
    """Guards the mutant `check_type in ("morning", "evening")` ->
    `check_type == "morning"` in adherence_rate_7d (eldercare_pulse.py:185).

    Under that mutation, evening check-ins vanish from the adherence
    denominator while every confirmation still lands in the numerator. The
    household consequence: evening doses go unconfirmed for a week, yet
    adherence reads perfect, needs_elevated_monitoring never trips, and the
    caregiver alert that exists precisely for a missed-medication pattern
    never fires. Her bedtime dose is simply gone and nobody is told.

    Nothing caught it because every check-in in every adherence test was
    check_type='morning'; no evening check-in ever entered the rate, so
    halving the denominator's scope was invisible. The property, not the
    instance: BOTH medication slots are denominator events, so an
    unconfirmed check-in in EITHER slot must drag the rate down equally.
    """

    @staticmethod
    def _checkin(check_type: str, confirmed: bool) -> CheckInResult:
        return CheckInResult(
            timestamp=datetime.now(timezone.utc),
            check_type=check_type,
            reached=True,  # reached but dose unconfirmed: adherence signal
            response="ok",  # only, never missed_checkins_this_week
            medication_confirmed=confirmed,
        )

    def test_unconfirmed_evening_checkins_lower_adherence(self):
        """One confirmed morning plus three unconfirmed evenings is 25%
        adherence. A week of missed bedtime doses must not read as 100%."""
        config = EldercarePulseConfig(_make_profile())
        config.record_checkin(self._checkin("morning", True))
        for _ in range(3):
            config.record_checkin(self._checkin("evening", False))
        assert config.adherence_rate_7d == 0.25, (
            "evening check-ins fell out of the adherence denominator -- "
            "missed bedtime doses are invisible to the rate")

    def test_missed_evening_pattern_trips_elevated_monitoring(self):
        """The alert this rate exists to drive: adherence below 0.5 caused
        by missed EVENING doses alone must still elevate monitoring."""
        config = EldercarePulseConfig(_make_profile())
        config.record_checkin(self._checkin("morning", True))
        for _ in range(3):
            config.record_checkin(self._checkin("evening", False))
        assert config.needs_elevated_monitoring, (
            "a week of unconfirmed evening doses did not trip elevated "
            "monitoring -- the missed-medication caregiver alert never fires")

    def test_both_slots_weigh_equally(self):
        """Symmetry: an unconfirmed morning and an unconfirmed evening must
        cost the rate the same. Guards the mirror mutant (== 'evening') and
        any rewrite that privileges one slot over the other."""
        morning_missed = EldercarePulseConfig(_make_profile())
        morning_missed.record_checkin(self._checkin("morning", False))
        morning_missed.record_checkin(self._checkin("evening", True))

        evening_missed = EldercarePulseConfig(_make_profile())
        evening_missed.record_checkin(self._checkin("morning", True))
        evening_missed.record_checkin(self._checkin("evening", False))

        assert morning_missed.adherence_rate_7d == 0.5
        assert evening_missed.adherence_rate_7d == 0.5
