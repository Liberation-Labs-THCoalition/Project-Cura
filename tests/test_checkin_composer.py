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
            memory_touches=[],
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
            memory_touches=[],
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


def _bob_config() -> EldercarePulseConfig:
    """The shape a real setup writes: one morning-only medication."""
    return EldercarePulseConfig(ElderProfile(
        name="Robert Edrington",
        preferred_name="Bob",
        phone="+15552223333",
        medications=[{"name": "Donepezil", "time": "morning"}],
        morning_time=9,
        evening_time=18,
    ))


class TestSpokenCheckinQuality:
    """These assert on what the elder actually hears — the full line sequence
    the rehearsal prints — rather than on any one fragment."""

    def _opens_with(self, line: str, name: str) -> bool:
        return line.startswith(name + ",") or line.startswith(name + ".")

    def test_only_the_greeting_opens_with_the_name(self):
        """The greeting has already said it. Anything after that opening with
        the name again is the "Bob. Bob," stutter."""
        composer = CheckinComposer()
        config = _bob_config()
        for messages in (composer.compose_morning(config).all_messages,
                         composer.compose_evening(config).all_messages):
            for line in messages[1:]:
                assert not self._opens_with(line, "Bob"), (messages[0], line)

    def test_no_single_line_says_the_name_twice(self):
        composer = CheckinComposer()
        config = _bob_config()
        for messages in (composer.compose_morning(config).all_messages,
                         composer.compose_evening(config).all_messages):
            for line in messages:
                assert line.count("Bob") <= 1, line

    def test_memory_touch_does_not_repeat_the_greeting_name(self):
        from cura.memory.companion_memory import CompanionMemory
        memory = CompanionMemory(elder_name="Bob")
        memory.add_event("Sarah's birthday", "2026-09-05", people=["Sarah"])
        composer = CheckinComposer(memory=memory)
        touches = composer.compose_morning(_bob_config()).memory_touches
        assert touches, "expected the seeded event to produce a touch"
        assert not touches[0].startswith("Bob")

    def test_morning_medication_is_not_repeated_in_the_evening(self):
        composer = CheckinComposer()
        config = _bob_config()
        evening = " ".join(composer.compose_evening(config).all_messages)
        assert "Donepezil" not in evening, evening
        morning = " ".join(composer.compose_morning(config).all_messages)
        assert "Donepezil" in morning

    def test_evening_medication_is_still_delivered(self):
        composer = CheckinComposer()
        config = EldercarePulseConfig(ElderProfile(
            name="Robert Edrington", preferred_name="Bob",
            medications=[{"name": "Amlodipine", "time": "evening"}],
        ))
        evening = " ".join(composer.compose_evening(config).all_messages)
        assert "Amlodipine" in evening
        morning = " ".join(composer.compose_morning(config).all_messages)
        assert "Amlodipine" not in morning
