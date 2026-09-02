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
        voice = CuraVoice(dry_run=True, public_url="https://cura.example.org")
        twiml = voice._build_twiml(
            ["Press 1"], gather=True,
            gather_action=voice._gather_url("/voice/checkin-response"))
        assert "<Gather" in twiml
        assert "timeout" in twiml
        assert "didn't hear" in twiml

    def test_gather_has_an_action_url(self):
        """A Gather without an action posts back to the URL that served the
        TwiML — and these calls are created with inline twiml=, which has no
        URL. The keypress went nowhere. Pressing 2 for help reached nobody."""
        voice = CuraVoice(dry_run=True, public_url="https://cura.example.org")
        twiml = voice._build_twiml(
            ["Press 1"], gather=True,
            gather_action=voice._gather_url("/voice/checkin-response"))
        assert 'action="https://cura.example.org/voice/checkin-response"' in twiml

    def test_no_gather_offered_when_the_answer_cannot_reach_us(self):
        """Better to not offer the button than to offer one that does nothing.
        Someone pressing 2 for help and hearing nothing back is the failure
        this whole path exists to prevent."""
        voice = CuraVoice(dry_run=True, public_url="")
        twiml = voice._build_twiml(["Press 1"], gather=True, gather_action="")
        assert "<Gather" not in twiml

    def test_relative_action_without_public_url_is_refused(self):
        """A relative path is unreachable to Twilio, which dials in from the
        public internet — and the failure is invisible from our side: the call
        completes and no response ever arrives."""
        voice = CuraVoice(dry_run=True, public_url="")
        assert voice._gather_url("/voice/checkin-response") == ""


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


class TestTwiMLEscaping:
    """Names and medications reach TwiML straight from the household's config.

    An ampersand or an angle bracket in either produces malformed XML that
    Twilio rejects, so the failure is not a mispronunciation -- it is a call
    that never happens. "Tylenol & Lisinopril" and a caregiver named
    "Tom & Barbara" were both enough to cancel every reminder silently.
    """

    HOSTILE = [
        "Tom & Barbara are coming by.",
        "Take 1 tablet if pain < 5 or > 7.",
        "Time for your Tylenol & Lisinopril.",
        'She said "I already took it".',
        "Hello</Say><Hangup/><Say>",
        """O'Brien & Sons <"test"> & more""",
    ]

    def _voice(self):
        from cura.comms.voice import CuraVoice
        return CuraVoice(account_sid="x", auth_token="y",
                         from_number="+15551112222",
                         public_url="https://example.org")

    @pytest.mark.parametrize("text", HOSTILE)
    def test_voice_twiml_stays_well_formed(self, text):
        import xml.etree.ElementTree as ET
        ET.fromstring(self._voice()._build_twiml([text]))

    @pytest.mark.parametrize("text", HOSTILE)
    def test_webhook_twiml_stays_well_formed(self, text):
        import xml.etree.ElementTree as ET
        from cura.comms import webhook as wh
        ET.fromstring(wh._twiml(wh._say(text)))

    @pytest.mark.parametrize("text", HOSTILE)
    def test_spoken_text_survives_verbatim(self, text):
        """Escaping must not change what she hears."""
        import xml.etree.ElementTree as ET
        root = ET.fromstring(self._voice()._build_twiml([text]))
        assert root.find("Say").text == text

    def test_markup_in_text_is_spoken_not_executed(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(
            self._voice()._build_twiml(["Hello</Say><Hangup/><Say>"]))
        assert root.find("Hangup") is None, "markup in a name became TwiML"
        assert root.find(".//Hangup") is None

    def test_attribute_injection_is_contained(self):
        """A poisoned public URL must not close the attribute and add verbs."""
        import xml.etree.ElementTree as ET
        v = self._voice()
        v._public_url = 'https://x.org/"><Hangup/><Gather action="'
        root = ET.fromstring(
            v._build_twiml(["hi"], gather=True,
                           gather_action=v._gather_url("/voice/r")))
        assert root.find(".//Hangup") is None
