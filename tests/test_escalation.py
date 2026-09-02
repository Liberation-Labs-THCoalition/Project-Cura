"""Escalation tests that can actually fail.

The suite had 157 passing tests and two mutants applied to the real escalation
code — blanking caregiver_phone, and misdirecting crisis_alert to dial the elder
instead of her contacts — passed all of them. `test_morning_checkin` asserted
`"Lisinopril" in t or "medication" in t`, which the constant line "Press 1 if
you've taken your medications" satisfies on its own.

Every test here was verified by mutation: the code it covers was deliberately
broken and the test was confirmed to notice. A test never observed failing is not
known to test anything.
"""
import asyncio
import logging

import pytest

from cura.comms.escalation import build_escalation, escalation_readiness
from cura.comms.responder import CuraResponder
from cura.pulse.eldercare_pulse import ElderProfile


def _profile(**over):
    base = dict(
        name="Margaret Chen", preferred_name="Mags", phone="+15551234567",
        medications=[], emergency_contacts=[{"name": "Thomas", "phone": "+15559876543"}],
        primary_caregiver={"name": "Thomas", "phone": "+15559876543"},
        address="", morning_time=8, evening_time=19,
    )
    base.update(over)
    return ElderProfile(**base)


class _FakeVoice:
    def __init__(self):
        self.calls = []

    async def crisis_alert(self, profile, crisis_type, details):
        self.calls.append({"profile": profile, "type": crisis_type, "details": details})
        return [("delivered", None)]


class TestReadiness:
    def test_no_contact_phone_blocks_escalation(self):
        """The GUI can write emergency_contacts: [] under a screen saying
        'Cura is ready.' That configuration must not be servable."""
        problems = escalation_readiness(_profile(emergency_contacts=[],
                                                 primary_caregiver={}))
        assert problems, "a profile with nobody to call reported itself ready"
        assert any("nobody can be reached" in p for p in problems)

    def test_contact_without_a_number_does_not_count(self):
        """A named contact with no phone is the plausible-looking config that
        produces silence at the worst moment."""
        problems = escalation_readiness(
            _profile(emergency_contacts=[{"name": "Thomas", "phone": ""}],
                     primary_caregiver={"name": "Thomas", "phone": ""}))
        assert problems

    def test_complete_profile_is_ready(self):
        assert escalation_readiness(_profile()) == []


class TestEscalationFires:
    def test_build_returns_none_when_help_cannot_be_summoned(self):
        """None is a refusal, not a degraded mode."""
        assert build_escalation(_FakeVoice(),
                                _profile(emergency_contacts=[],
                                         primary_caregiver={})) is None

    def test_callback_actually_calls_crisis_alert(self):
        voice = _FakeVoice()
        cb = build_escalation(voice, _profile())
        assert cb is not None
        cb("Elder said: I fell and I can't get up")
        assert len(voice.calls) == 1, "help was requested and nobody was contacted"
        assert "fell" in voice.calls[0]["details"]

    def test_crisis_alert_receives_the_profile_with_the_contacts(self):
        """Guards the mutant that dialled the elder instead of her contacts."""
        voice = _FakeVoice()
        build_escalation(voice, _profile())("help")
        sent_to = voice.calls[0]["profile"].emergency_contacts
        assert sent_to and sent_to[0]["phone"] == "+15559876543"


class TestResponderPromise:
    def test_unwired_responder_does_not_promise_help(self):
        """The defect that started this: Cura told someone who had fallen that
        help was on the way while on_help_requested was None."""
        r = CuraResponder()
        said = r.handle_speech("I fell in the pantry and I can't get up")["say"].lower()
        assert "help is on the way" not in said
        assert "911" in said or "nine one one" in said

    def test_wired_responder_promises_and_delivers(self):
        got = []
        r = CuraResponder(on_help_requested=lambda m: got.append(m))
        said = r.handle_speech("I fell and I can't get up")["say"].lower()
        assert "help is on the way" in said
        assert got, "Cura promised help and did not call the callback"

    def test_warm_wording_survives(self):
        """A first attempt at the safety fix flattened three responses into one
        and lost 'You're not alone' — the warmest thing Cura says."""
        r = CuraResponder(on_help_requested=lambda m: None)
        assert "not alone" in r.handle_dtmf("2", "checkin")["say"].lower()

    def test_unwired_responder_logs_an_error(self, caplog):
        """Silence about a failed escalation is how this stayed broken."""
        with caplog.at_level(logging.ERROR):
            CuraResponder().handle_dtmf("2", "checkin")
        assert any("NO CALLBACK" in r.message.upper() or
                   "no callback" in r.getMessage().lower() for r in caplog.records)
