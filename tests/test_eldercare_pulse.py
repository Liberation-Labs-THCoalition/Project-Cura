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
