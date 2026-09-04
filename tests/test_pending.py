"""Remembering what Cura just asked, so the answer has somewhere to go.

Cura asked "do you have grab bars in your bathroom?", she answered, handle_speech
matched no keywords and fell through to "Thank you for sharing that with me."
The answer was discarded, record_concern had never been called by anything, and
get_summary() reported "no concerns identified" every time — with a test
asserting that it did.

The missing piece was not a handler. It was memory of the question.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cura.comms.pending import (PendingQuestion, interpret_yes_no,
                                load_pending, save_pending)
from cura.comms.responder import CuraResponder
from cura.pulse.daily_enrichments import HomeSafetyAssessment


class TestUncertaintyIsNotANo:
    """"I don't know" recorded as "no, there are no grab bars" is a false fact
    in a safety record. My first version returned False for it, because "i
    don't" is in the NO prefixes and was checked first."""

    @pytest.mark.parametrize("said", [
        "I don't know", "not sure", "I can't remember", "no idea",
        "maybe", "I think so", "what?", "", "mm", "sometimes",
    ])
    def test_it_returns_none(self, said):
        assert interpret_yes_no(said) is None

    @pytest.mark.parametrize("said,expect", [
        ("yes", True), ("yeah we have them", True), ("we do", True),
        ("no", False), ("there isn't one", False),
        ("no, none in the shower", False), ("nope", False),
    ])
    def test_clear_answers_are_read(self, said, expect):
        assert interpret_yes_no(said) is expect

    def test_a_bare_murmur_is_not_agreement(self):
        """Acquiescence bias runs toward yes. A murmur must not become one."""
        assert interpret_yes_no("mm") is None
        assert interpret_yes_no("mmhm...") is not True


class TestTheAnswerReachesTheAssessment:
    def test_a_no_becomes_a_recorded_concern(self):
        assess = HomeSafetyAssessment()
        assess.get_next_question()
        r = CuraResponder()
        r.expect_answer("home_safety", handler=lambda ans, txt: (
            assess.record_concern(0, txt) if ans is False else None))
        out = r.handle_speech("no, there aren't any in the shower")
        assert out["action"] == "home_safety_answered"
        assert "1 concern" in assess.get_summary()
        assert "no concerns identified" not in assess.get_summary()

    def test_an_unclear_answer_records_nothing(self):
        assess = HomeSafetyAssessment()
        assess.get_next_question()
        r = CuraResponder()
        r.expect_answer("home_safety", handler=lambda ans, txt: (
            assess.record_concern(0, txt) if ans is False else None))
        out = r.handle_speech("I don't know, I can't remember")
        assert out["action"] == "home_safety_unclear"
        assert "no concerns identified" not in assess.get_summary()


class TestAPendingQuestionNeverSwallowsAnEmergency:
    """If Cura asked about grab bars and she says "I've fallen and I can't get
    up", that is not an answer about grab bars."""

    @pytest.mark.parametrize("said", [
        "I've fallen and I can't get up", "help", "I'm hurt",
        "I fell in the bathroom", "I'm in pain",
    ])
    def test_help_wins_over_the_pending_question(self, said):
        fired = []
        r = CuraResponder(on_help_requested=fired.append)
        r.expect_answer("home_safety", handler=lambda *a: fired.append("SURVEY"))
        out = r.handle_speech(said)
        assert out["action"] == "help_requested"
        assert "SURVEY" not in fired

    def test_a_scam_report_also_wins(self):
        seen = []
        r = CuraResponder(on_scam_report=seen.append)
        r.expect_answer("home_safety", handler=lambda *a: seen.append("SURVEY"))
        out = r.handle_speech("someone called and asked for money")
        assert out["action"] == "scam_report"
        assert "SURVEY" not in seen


class TestExpiryAndConsumption:
    def test_a_stale_question_is_not_answered(self, tmp_path):
        """An answer tomorrow is not an answer to what was asked. Better to
        lose one than to file an unrelated sentence as one."""
        p = tmp_path / "pq.json"
        save_pending("home_safety", datetime.now(timezone.utc) - timedelta(hours=2),
                     path=p)
        assert load_pending(path=p) is None

    def test_it_is_consumed_on_read(self, tmp_path):
        """One question yields at most one answer. A question that survived its
        answer would attach the NEXT thing she says to a completed survey."""
        p = tmp_path / "pq.json"
        save_pending("home_safety", datetime.now(timezone.utc), path=p)
        assert load_pending(path=p) is not None
        assert load_pending(path=p) is None

    def test_long_pauses_are_tolerated(self):
        """Thomas: long pauses are common in the elderly, especially as they
        sunset. The window is generous on purpose."""
        q = PendingQuestion("home_safety",
                            datetime.now(timezone.utc) - timedelta(minutes=3))
        assert q.expired() is False

    def test_the_file_is_private(self, tmp_path):
        p = tmp_path / "pq.json"
        save_pending("home_safety", datetime.now(timezone.utc), path=p)
        assert oct(p.stat().st_mode & 0o777) == "0o600"


class TestItCrossesTheProcessBoundary:
    """`cura run` places the call that asks; `cura webhook` hears the reply.
    In-memory only would have made this another correct half."""

    def test_a_question_asked_elsewhere_is_still_answerable(self, tmp_path,
                                                            monkeypatch):
        from cura.comms import pending
        p = tmp_path / "pq.json"
        monkeypatch.setattr(pending, "PENDING_FILE", p)
        save_pending("home_safety", datetime.now(timezone.utc), path=p)
        fresh = CuraResponder()          # a different process's responder
        out = fresh.handle_speech("no, we don't have any")
        assert out["action"] == "home_safety_answered"
