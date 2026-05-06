"""Tests for voice interface — Cura's Twilio integration."""
from __future__ import annotations

import pytest
from cura.comms.voice import CuraVoice, CallResult, SMSResult
from cura.pulse.eldercare_pulse import ElderProfile


def _make_profile() -> ElderProfile:
    return ElderProfile(
        name="Margaret Chen",
        preferred_name="Margaret",
        phone="+15551234567",
        medications=[
            {"name": "Lisinopril", "time": "morning"},
            {"name": "Metformin", "time": "morning"},
            {"name": "Amlodipine", "time": "evening PM"},
        ],
        emergency_contacts=[
            {"name": "Sarah Chen", "phone": "+15559876543", "relation": "daughter"},
            {"name": "Tom Chen", "phone": "+15559876544", "relation": "son"},
        ],
        primary_caregiver={"name": "Sarah Chen", "phone": "+15559876543"},
        address="123 Elm Street, Springfield, IL",
    )


class TestTwiMLGeneration:
    def test_basic_twiml(self):
        voice = CuraVoice(dry_run=True)
        twiml = voice._build_twiml(["Hello Margaret"])
        assert "<Say" in twiml
        assert "Hello Margaret" in twiml
        assert "<Pause" in twiml

    def test_gather_twiml(self):
        voice = CuraVoice(dry_run=True)
        twiml = voice._build_twiml(["Press 1"], gather=True)
        assert "<Gather" in twiml
        assert "timeout" in twiml
        assert "didn't hear" in twiml


@pytest.mark.asyncio
class TestDryRunCalls:
    async def test_basic_call(self):
        voice = CuraVoice(dry_run=True)
        result = await voice.call("+15551234567", ["Hello"])
        assert result.answered
        assert result.call_sid == "dry_run"

    async def test_send_sms(self):
        voice = CuraVoice(dry_run=True)
        result = await voice.send_sms("+15551234567", "Test message")
        assert result.delivered
        assert result.message_sid == "dry_run"

    async def test_morning_checkin(self):
        voice = CuraVoice(dry_run=True)
        profile = _make_profile()
        result = await voice.morning_checkin(profile)
        assert result.answered
        assert "Lisinopril" in result.transcript or "medication" in result.transcript

    async def test_evening_checkin(self):
        voice = CuraVoice(dry_run=True)
        profile = _make_profile()
        result = await voice.evening_checkin(profile)
        assert result.answered

    async def test_alert_caregiver(self):
        voice = CuraVoice(dry_run=True)
        profile = _make_profile()
        call_result, sms_result = await voice.alert_caregiver(
            profile, "missed_checkin", "Margaret didn't answer morning check-in"
        )
        assert call_result.answered
        assert sms_result.delivered

    async def test_crisis_alert_contacts_all(self):
        voice = CuraVoice(dry_run=True)
        profile = _make_profile()
        results = await voice.crisis_alert(profile, "fall", "Fall detected at 2am")
        assert len(results) == 2

    async def test_call_log(self):
        voice = CuraVoice(dry_run=True)
        await voice.call("+15551234567", ["Test"])
        await voice.call("+15559876543", ["Test 2"])
        assert len(voice.call_log) == 2

    async def test_sms_log(self):
        voice = CuraVoice(dry_run=True)
        await voice.send_sms("+15551234567", "Test")
        assert len(voice.sms_log) == 1
