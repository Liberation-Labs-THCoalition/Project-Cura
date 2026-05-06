"""Tests for responder — Cura's ears."""
from __future__ import annotations

from cura.comms.responder import CuraResponder


class TestDTMF:
    def test_press_1_confirms_meds(self):
        confirmed = []
        responder = CuraResponder(on_medication_confirmed=lambda: confirmed.append(True))
        result = responder.handle_dtmf("1", "checkin")
        assert result["action"] == "medication_confirmed"
        assert len(confirmed) == 1

    def test_press_2_requests_help(self):
        alerts = []
        responder = CuraResponder(on_help_requested=lambda msg: alerts.append(msg))
        result = responder.handle_dtmf("2", "checkin")
        assert result["action"] == "help_requested"
        assert len(alerts) == 1
        assert "not alone" in result["say"].lower()

    def test_press_9_repeats(self):
        responder = CuraResponder()
        result = responder.handle_dtmf("9", "checkin")
        assert result["action"] == "repeat"

    def test_unknown_digit(self):
        responder = CuraResponder()
        result = responder.handle_dtmf("7", "checkin")
        assert result["action"] == "unknown"

    def test_evening_press_2_goodnight(self):
        responder = CuraResponder()
        result = responder.handle_dtmf("2", "evening")
        assert result["action"] == "all_good"
        assert "sleep well" in result["say"].lower()


class TestSpeech:
    def test_help_request(self):
        alerts = []
        responder = CuraResponder(on_help_requested=lambda msg: alerts.append(msg))
        result = responder.handle_speech("I fell and I'm hurt")
        assert result["action"] == "help_requested"
        assert len(alerts) == 1

    def test_scam_report(self):
        reports = []
        responder = CuraResponder(on_scam_report=lambda msg: reports.append(msg))
        result = responder.handle_speech("Someone called asking for gift cards")
        assert result["action"] == "scam_report"
        assert len(reports) == 1
        assert "right thing" in result["say"].lower()

    def test_general_conversation(self):
        responder = CuraResponder()
        result = responder.handle_speech("I had a nice walk in the garden today")
        assert result["action"] == "conversation"

    def test_speech_callback(self):
        transcripts = []
        responder = CuraResponder(on_speech=lambda t: transcripts.append(t))
        responder.handle_speech("Hello there")
        assert len(transcripts) == 1


class TestInbound:
    def test_greeting(self):
        responder = CuraResponder()
        greeting = responder.build_inbound_greeting("Margaret")
        assert "Margaret" in greeting
        assert "glad you called" in greeting.lower()

    def test_menu(self):
        responder = CuraResponder()
        menu = responder.build_inbound_menu()
        assert "Press 1" in menu
        assert "Press 4" in menu

    def test_chat_choice(self):
        responder = CuraResponder()
        result = responder.handle_inbound_choice("1", "Margaret")
        assert result["action"] == "chat"
        assert "Margaret" in result["say"]

    def test_medication_choice(self):
        responder = CuraResponder()
        result = responder.handle_inbound_choice("2", "Margaret")
        assert result["action"] == "medication_question"

    def test_scam_choice(self):
        responder = CuraResponder()
        result = responder.handle_inbound_choice("3", "Margaret")
        assert result["action"] == "scam_report"

    def test_help_choice(self):
        alerts = []
        responder = CuraResponder(on_help_requested=lambda msg: alerts.append(msg))
        result = responder.handle_inbound_choice("4", "Margaret")
        assert result["action"] == "help_requested"
        assert len(alerts) == 1
        assert "not alone" in result["say"].lower()

    def test_response_log(self):
        responder = CuraResponder()
        responder.handle_dtmf("1", "checkin")
        responder.handle_speech("hello", "inbound")
        assert len(responder.response_log) == 2
