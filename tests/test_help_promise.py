"""Cura promises help only when help was actually summoned (Vera, 2026-09-24).

Digit 4 on an inbound call said "I'm contacting your family right now" whatever
happened: no callback, a callback that raised, or an escalation that reached
nobody. These tests pin the promise to the escalation's own verdict through the
responder, both help callbacks, and the production webhook route.
"""
import pytest

from cura.comms.escalation import build_escalation, build_ladder_escalation
from cura.comms.responder import CuraResponder
from cura.comms.webhook import create_app
from tests.test_escalation import _FakeVoice, _profile
from tests.test_ladder import THOMAS, TestTheLadderIsActuallyWired, _house

WARM = "contacting your family"
FALLBACK = "nine one one"


def _raise(msg):
    raise RuntimeError("provider down")


@pytest.mark.parametrize("callback", [None, lambda m: False, _raise],
                         ids=["no-callback", "reached-nobody", "raised"])
def test_digit_4_does_not_promise_help_that_was_not_summoned(callback):
    say = CuraResponder(on_help_requested=callback).handle_inbound_choice("4", "Margaret")["say"].lower()
    assert WARM not in say and FALLBACK in say


@pytest.mark.parametrize("verdict", [True, None], ids=["reached", "in-progress"])
def test_digit_4_promises_help_that_was_summoned(verdict):
    calls = []

    def cb(msg):
        calls.append(msg)
        return verdict
    say = CuraResponder(on_help_requested=cb).handle_inbound_choice("4", "Margaret")["say"].lower()
    assert calls and WARM in say and "not alone" in say


@pytest.mark.parametrize("verdict,hears_warm", [(False, False), (True, True)],
                         ids=["reached-nobody", "reached"])
def test_the_webhook_speaks_the_truth_on_digit_4(verdict, hears_warm):
    # Signed the way Twilio signs, so the route's signature check stays on.
    from twilio.request_validator import RequestValidator
    token, base, form = "test-token-not-a-secret", "https://cura.test", {"Digits": "4"}
    app = create_app(responder=CuraResponder(on_help_requested=lambda m: verdict),
                     elder_name="Margaret", auth_token=token, public_url=base)
    sig = RequestValidator(token).compute_signature(base + "/voice/inbound-response", form)
    r = app.test_client().post("/voice/inbound-response", data=form,
                               headers={"X-Twilio-Signature": sig})
    body = r.get_data(as_text=True).lower()
    assert r.status_code == 200, body[:200]
    assert (WARM in body) is hears_warm
    assert (FALLBACK in body) is (not hears_warm)


class _Voice(_FakeVoice):
    def __init__(self, results=None, raises=False):
        super().__init__()
        self.results, self.raises = results, raises

    async def crisis_alert(self, profile, crisis_type, details):
        if self.raises:
            raise RuntimeError("provider down")
        await super().crisis_alert(profile, crisis_type, details)
        return self.results


@pytest.mark.parametrize("voice,expected", [
    (_Voice(results=[("delivered", None)]), True),
    (_Voice(results=[None, False]), False),
    (_Voice(raises=True), False),
], ids=["delivered", "every-contact-failed", "raised"])
def test_the_simple_callback_reports_its_outcome(voice, expected):
    assert build_escalation(voice, _profile())("help") is expected


def test_the_ladder_callback_reports_its_outcome(monkeypatch):
    V = TestTheLadderIsActuallyWired._Voice
    reached = build_ladder_escalation(V(answers=("+15305551234",)), _house(thomas=THOMAS), "ray")
    assert reached("x") is True
    unanswered = build_ladder_escalation(V(answers=()), _house(thomas=THOMAS), "ray")
    assert unanswered("x") is False

    import cura.comms.ladder as ladder

    def down(*a, **k):
        raise RuntimeError("provider down")
    monkeypatch.setattr(ladder, "climb", down)
    assert build_ladder_escalation(V(answers=()), _house(thomas=THOMAS), "ray")("x") is False
