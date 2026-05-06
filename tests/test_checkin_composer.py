"""Tests for check-in composer — wiring enrichments into check-ins."""
from __future__ import annotations

from cura.pulse.checkin_composer import CheckinComposer, ComposedCheckin
from cura.pulse.eldercare_pulse import ElderProfile, EldercarePulseConfig


def _make_config() -> EldercarePulseConfig:
    profile = ElderProfile(
        name="Margaret Chen",
        preferred_name="Margaret",
        phone="+15551234567",
        medications=[{"name": "Lisinopril", "time": "morning"}],
        emergency_contacts=[{"name": "Sarah", "phone": "+15559876543"}],
        primary_caregiver={"name": "Sarah", "phone": "+15559876543"},
    )
    return EldercarePulseConfig(profile)


class TestComposedCheckin:
    def test_all_messages_includes_greeting(self):
        checkin = ComposedCheckin(
            greeting="Good morning",
            medication_reminder="Take your pills",
            enrichments=[],
            wearable_observations=[],
            scam_addition=None,
        )
        msgs = checkin.all_messages
        assert msgs[0] == "Good morning"
        assert msgs[1] == "Take your pills"

    def test_all_messages_includes_enrichments(self):
        from cura.pulse.daily_enrichments import Enrichment
        checkin = ComposedCheckin(
            greeting="Hi",
            medication_reminder="",
            enrichments=[Enrichment("test", "Drink water", 0.5)],
            wearable_observations=[],
            scam_addition="Safety tip: don't click links",
        )
        msgs = checkin.all_messages
        assert "Drink water" in msgs
        assert "Safety tip" in msgs[-1]


class TestCheckinComposer:
    def test_morning_checkin_has_greeting(self):
        composer = CheckinComposer()
        config = _make_config()
        checkin = composer.compose_morning(config)
        assert "Margaret" in checkin.greeting

    def test_morning_checkin_has_medication(self):
        composer = CheckinComposer()
        config = _make_config()
        checkin = composer.compose_morning(config)
        assert "Lisinopril" in checkin.medication_reminder

    def test_morning_respects_max_enrichments(self):
        composer = CheckinComposer(max_enrichments=2)
        config = _make_config()
        checkin = composer.compose_morning(config, weather={"temp_f": 100})
        assert len(checkin.enrichments) <= 2

    def test_hot_weather_prioritized(self):
        composer = CheckinComposer()
        config = _make_config()
        checkin = composer.compose_morning(config, weather={"temp_f": 100})
        categories = [e.category for e in checkin.enrichments]
        assert "weather" in categories or "hydration" in categories

    def test_evening_checkin(self):
        composer = CheckinComposer()
        config = _make_config()
        checkin = composer.compose_evening(config)
        assert "Margaret" in checkin.greeting
        assert len(checkin.enrichments) <= 3

    def test_all_messages_is_list(self):
        composer = CheckinComposer()
        config = _make_config()
        checkin = composer.compose_morning(config)
        msgs = checkin.all_messages
        assert isinstance(msgs, list)
        assert len(msgs) >= 2
