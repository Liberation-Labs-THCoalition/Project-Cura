"""Cura never says it is telling the family when nothing is sent (Lane 6, 2026-11-14).

The console and the MCP server both answered a frightened person with "I'm
alerting your family right now. Stay calm, stay where you are. You're not
alone." Neither can reach anyone: no phone line, no contacts, no escalation
callback. Nobody was alerted, and "stay where you are" told someone who had
fallen to wait for help that was not coming. The phone path closed this in
cura/comms/responder.py::_promise_help; these two surfaces were missed. Their
scam branches made the same claim ("I'm flagging this for your family right
away", "I'm going to let your family know"), with the alert kept in memory and
sent nowhere. So did the phone: production wires no scam callback, and the
responder still said "I'm going to let your family know"; so did the README.

Each test drives the real entry point (`cura console` through cura.__main__,
and the MCP server's own call_tool handler) with every sending primitive Cura
has replaced by a recorder. The rule it checks is the lane's: the text may
claim an alert only if one was sent. Nothing is sent on these surfaces today,
so a claim fails the test; if someone later wires a real alert in, the claim
becomes allowed without editing this file.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# --- What counts as a claim -------------------------------------------------

#: Who a claim can say was told or sent for. Widened 11-21: the batch 11
#: verifier put "I'm calling 911 for you now" and "Your daughter has been
#: notified" on the fixed lines and the suite passed.
_WHO = (r"(?:family|caregiver|daughter|son|wife|husband|people|someone|anyone|help|"
        r"911|nine one one|an ambulance|emergency services|the police|paramedics)")
#: A first-person promise that someone is being, will be, or has been told or
#: sent for ("I'm alerting", "I'll call", "I've let", "I told").
_FIRST_PERSON = re.compile(
    r"\bI(?:'m| am|'ll| will|'ve| have)?(?: going to| just)?\s+(?:\w+\s+)?"
    r"(?:alert|flag|let|tell|told|contact|notif|call|ring|rang|reach|text|messag|"
    r"send|sent|pass|get|got)\w*\b"
    rf"[^.!?]*\b{_WHO}\b",
    re.IGNORECASE)
#: The same promise in the passive voice ("Your daughter has been notified").
_PASSIVE = re.compile(
    r"\b(?:family|caregiver|daughter|son|wife|husband|people)\b[^.!?]*\b"
    r"(?:is|are|was|were|has been|have been|will be)\s+"
    r"(?:being\s+)?(?:alerted|told|notified|contacted|called|flagged|informed|sent for)\b",
    re.IGNORECASE)
#: Words that only make sense if someone is on the way ("Help is on its way").
_ARRIVING = re.compile(
    r"help is (?:on (?:the|its) way|coming)|someone will (?:check on|come)|"
    r"stay where you are|(?:is|are) on (?:the|its|their|her|his) way",
    re.IGNORECASE)
#: The press-two line's present-tense forms ("That reaches your family",
#: "two gets your family"): true only where a key and a ladder exist.
_REACHES = re.compile(
    r"\b(?:that|two|it|this)\s+(?:reaches|gets|rings|calls)\s+your\s+(?:family|people)\b",
    re.IGNORECASE)
#: Something was done about it ("flagged and handled").
_HANDLED = re.compile(r"\bflagged and handled\b|\bhas been handled\b|\btaken care of\b",
                      re.IGNORECASE)


def _text_claims_alert(text: str) -> list[str]:
    return [m.group(0) for p in (_FIRST_PERSON, _PASSIVE, _ARRIVING, _REACHES, _HANDLED)
            for m in p.finditer(text)]


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def _payload_claims_alert(payload: dict) -> list[str]:
    """A claim in the data counts as much as one in the words: an MCP host
    reads "action": "alert_caregiver" as something Cura did."""
    found = [c for s in _strings(payload) for c in _text_claims_alert(s)]
    if payload.get("action") == "alert_caregiver":
        found.append('"action": "alert_caregiver"')
    if payload.get("caregiver_alerted") is True:
        found.append('"caregiver_alerted": true')
    if payload.get("caregiver_notify"):
        found.append('"caregiver_notify": true')
    return found


# The sentences these surfaces used to say, verbatim. The detector must catch
# every one of them, or a revert would pass the tests below.
HISTORIC_FALSE_SENTENCES = [
    "Margaret, I hear you. I'm alerting your family right now. "
    "Stay calm, stay where you are. You're not alone.",
    "I'm flagging this for your family right away. "
    "You did absolutely the right thing telling me.",
    "Thank you for telling me about that. You did the right thing. "
    "I'm going to let your family know so they can help look into it. "
    "Remember, it's never wrong to check with someone you trust before "
    "giving out information or sending money.",
    "Thank you for telling me about that. You did the right thing. "
    "I'm going to let your family know so they can help look into it. "
    "Remember, it's never wrong to check with someone you trust.",
]


#: False claims the batch 11 verifier put on the fixed lines; all five passed the
#: suite (857 passed) before the detector was widened. Plus the press-two
#: line's forms the detector missed, and the summary's "handled".
VERIFIER_SURVIVORS = [
    "Margaret, I hear you. I've let your family know.",
    "Margaret, I hear you. I'm calling 911 for you now.",
    "Your daughter has been notified.",
    "Help is on its way.",
    "Thank you for telling me about that. I've told your family, but please tell them too.",
    "And if you need anything at all, press two. That reaches your family.",
    "And the usual: two gets your family.",
    "If you ever need help, press two and I'll call your family.",
    "Same as always, press two and I'll call your people.",
    "SCAM DEFENSE: 1 suspicious contact(s) flagged and handled",
]


@pytest.mark.parametrize("sentence", HISTORIC_FALSE_SENTENCES + VERIFIER_SURVIVORS)
def test_the_detector_catches_each_sentence_that_was_said(sentence):
    assert _text_claims_alert(sentence), sentence


def test_the_detector_passes_the_honest_lines_that_name_who_to_call():
    """Telling her to call 911 is not a claim that Cura did."""
    from cura.comms.responder import CANNOT_REACH_ANYONE as PHONE
    from cura.pulse.help_prompt import NO_KEYPAD_HELP_LINE
    for line in (PHONE, NO_KEYPAD_HELP_LINE):
        assert _text_claims_alert(line) == [], line


def test_the_detector_passes_the_sentences_that_replaced_them():
    from cura.console import CANNOT_REACH_ANYONE
    from cura.privacy.scam_shield import ScamShield
    assert _text_claims_alert(CANNOT_REACH_ANYONE) == []
    assert _text_claims_alert(ScamShield().get_reassurance()) == []


def test_the_reassurance_claims_the_family_only_when_the_caller_says_so():
    """The default claims nothing; family_told=True is the only way to the
    family sentence, for a caller that really passed the report on."""
    from cura.privacy.scam_shield import ScamShield
    shield = ScamShield()
    assert _text_claims_alert(shield.get_reassurance(family_told=False)) == []
    assert _text_claims_alert(shield.get_reassurance(family_told=True))
    assert shield.get_reassurance() == shield.get_reassurance(family_told=False)


# --- Recording every way Cura can send ---------------------------------------

@pytest.fixture
def sent(monkeypatch):
    """Replace every primitive that reaches a person with a recorder.

    The leaves, not the builders: both escalation callbacks end in a CuraVoice
    method or ladder.climb, and a builder left real lets the production
    responder be built as `cura webhook` builds it."""
    log: list[str] = []
    from cura.comms import voice as voice_mod, ladder

    def _rec(label):
        def f(*a, **k):
            log.append(label)
            return None
        return f

    def _arec(label):
        async def f(*a, **k):
            log.append(label)
            return None
        return f

    for meth in ("call", "send_sms", "alert_caregiver", "crisis_alert",
                 "morning_checkin", "evening_checkin"):
        monkeypatch.setattr(voice_mod.CuraVoice, meth, _arec(f"CuraVoice.{meth}"))
    monkeypatch.setattr(ladder, "climb", _rec("ladder.climb"))
    return log


# --- The console, through `cura console` -------------------------------------

def _console(monkeypatch, capsys, said: str) -> str:
    lines = iter([said, "bye"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    monkeypatch.setattr(sys, "argv", ["cura", "console", "--name", "Margaret"])
    from cura.__main__ import main
    main()
    return capsys.readouterr().out


CRISIS_SAID = [
    "I fell and I can't get up",
    "help me please",
    "this is an emergency",
    "I hurt my hip",
    "I'm in a lot of pain",
    "I'm scared",
]


@pytest.mark.parametrize("said", CRISIS_SAID)
def test_the_console_claims_no_alert_it_did_not_send(said, sent, monkeypatch, capsys):
    out = _console(monkeypatch, capsys, said)
    claims = _text_claims_alert(out)
    assert not claims or sent, f"claimed {claims} with nothing sent:\n{out}"
    assert "I hear you" in out, out          # the crisis branch answered
    if not sent:
        assert "911" in out, f"nothing was sent and no one to call was named:\n{out}"


#: (what she says, whether the scam shield rates it 0.8 or more)
SCAM_SAID = [
    ("My grandson called and said he's in jail", False),
    ("They want me to wire money today", True),
    ("A man said I won a prize, buy a gift card and keep it between us", True),
]


@pytest.mark.parametrize("said,high", SCAM_SAID)
def test_the_console_claims_no_scam_report_it_did_not_pass_on(said, high, sent,
                                                              monkeypatch, capsys):
    out = _console(monkeypatch, capsys, said)
    claims = _text_claims_alert(out)
    assert not claims or sent, f"claimed {claims} with nothing sent:\n{out}"
    assert "right thing" in out, out         # the scam branch answered
    if not sent:
        assert "please tell them" in out, f"nothing was sent and she was not asked to tell anyone:\n{out}"
    assert ("worries me" in out) is high, out


# --- The MCP server, through its own call_tool handler ------------------------

class _FakeServer:
    """Stands in for mcp.server.Server: keeps the handlers the code registers."""

    def __init__(self, name):
        self.handlers = {}

    def _register(self, key):
        def deco(fn):
            self.handlers[key] = fn
            return fn
        return deco

    def list_tools(self):
        return self._register("list_tools")

    def call_tool(self):
        return self._register("call_tool")

    def list_resources(self):
        return self._register("list_resources")

    def read_resource(self):
        return self._register("read_resource")


class _Content:
    def __init__(self, type, text):
        self.type, self.text = type, text


@pytest.fixture
def mcp_call(monkeypatch, tmp_path):
    """The real cura_mcp_server, loaded against a stand-in MCP SDK.

    The SDK is not installed in the test venv, which is why the other server
    tests parse the source. This one runs the handler instead, so it checks
    what the server says, not what its source looks like."""
    mcp = types.ModuleType("mcp")
    server = types.ModuleType("mcp.server")
    server.Server = _FakeServer
    stdio = types.ModuleType("mcp.server.stdio")
    stdio.stdio_server = None
    mtypes = types.ModuleType("mcp.types")
    mtypes.Tool = mtypes.Resource = lambda **k: k
    mtypes.TextContent = _Content
    for name, mod in (("mcp", mcp), ("mcp.server", server),
                      ("mcp.server.stdio", stdio), ("mcp.types", mtypes)):
        monkeypatch.setitem(sys.modules, name, mod)

    spec = importlib.util.spec_from_file_location(
        "_cura_mcp_server_under_test", ROOT / "cura_mcp_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.HAS_MCP, "the stand-in SDK was not picked up"
    srv = module.create_server("Margaret", data_dir=str(tmp_path / "memory"))

    def call(tool: str, args: dict) -> dict:
        out = asyncio.run(srv.handlers["call_tool"](tool, args))
        return json.loads(out[0].text)
    return call


@pytest.mark.parametrize("said", CRISIS_SAID)
def test_the_mcp_server_claims_no_alert_it_did_not_send(said, sent, mcp_call):
    payload = mcp_call("cura_ask", {"message": said})
    assert payload["status"] == "crisis", payload
    claims = _payload_claims_alert(payload)
    assert not claims or sent, f"claimed {claims} with nothing sent: {payload}"
    assert payload["caregiver_alerted"] is bool(sent), payload
    if not sent:
        assert "911" in payload["response"], payload


@pytest.mark.parametrize("said,high", SCAM_SAID)
def test_the_mcp_ask_claims_no_scam_report_it_did_not_pass_on(said, high, sent, mcp_call):
    payload = mcp_call("cura_ask", {"message": said})
    assert payload["status"] == "scam_alert", payload
    claims = _payload_claims_alert(payload)
    assert not claims or sent, f"claimed {claims} with nothing sent: {payload}"
    assert payload["caregiver_alerted"] is bool(sent), payload
    assert payload["caregiver_should_be_told"] is high, payload
    if not sent:
        assert "please tell them" in payload["response"], payload


@pytest.mark.parametrize("said,high", SCAM_SAID)
def test_the_mcp_scam_check_claims_no_report_it_did_not_pass_on(said, high, sent, mcp_call):
    payload = mcp_call("cura_scam_check", {"message": said})
    assert payload["status"] == "alert", payload
    claims = _payload_claims_alert(payload)
    assert not claims or sent, f"claimed {claims} with nothing sent: {payload}"
    assert payload["caregiver_alerted"] is bool(sent), payload


# --- The phone, as `cura webhook` builds it ------------------------------------

#: Scam reports the responder hears; none contains a help word, which wins first.
PHONE_SCAM_SAID = [
    "Someone called and asked for my bank number",
    "A man wants me to buy a gift card",
    "I got a weird call about my Medicare",
    "I think that email was a scam",
]


def _production_responder(tmp_path):
    from cura.__main__ import _build_responder
    from tests.test_production_seam import _wizard_config
    return _build_responder(str(_wizard_config(tmp_path)))


@pytest.mark.parametrize("context", ["checkin", "evening", "inbound"])
@pytest.mark.parametrize("said", PHONE_SCAM_SAID)
def test_the_phone_claims_no_scam_report_it_did_not_pass_on(said, context, sent, tmp_path):
    out = _production_responder(tmp_path).handle_speech(said, context)
    assert out["action"] == "scam_report", out
    claims = _text_claims_alert(out["say"])
    assert not claims or sent, f"claimed {claims} with nothing sent: {out}"
    if not sent:
        assert "please tell them" in out["say"], out


def test_the_webhook_speaks_the_truth_about_a_scam_report(sent, tmp_path):
    """The sentence that reaches the caller's ear, through the signed route."""
    import html
    from twilio.request_validator import RequestValidator
    from cura.comms.webhook import create_app
    token, base = "test-token-not-a-secret", "https://cura.test"
    form = {"SpeechResult": "Someone called and asked for money"}
    app = create_app(responder=_production_responder(tmp_path),
                     elder_name="Margaret", auth_token=token, public_url=base)
    sig = RequestValidator(token).compute_signature(base + "/voice/checkin-response", form)
    r = app.test_client().post("/voice/checkin-response", data=form,
                               headers={"X-Twilio-Signature": sig})
    body = html.unescape(r.get_data(as_text=True))   # TwiML escapes the apostrophes
    assert r.status_code == 200, body[:200]
    claims = _text_claims_alert(body)
    assert not claims or sent, f"claimed {claims} with nothing sent: {body}"
    assert "please tell them" in body, body


def _raise(transcript):
    raise RuntimeError("provider down")


@pytest.mark.parametrize("callback", [None, lambda t: False, _raise],
                         ids=["no-callback", "not-passed-on", "raised"])
def test_the_phone_asks_her_to_tell_them_when_the_report_went_nowhere(callback):
    from cura.comms.responder import CuraResponder
    say = CuraResponder(on_scam_report=callback).handle_speech(
        "Someone called asking for gift cards")["say"]
    assert _text_claims_alert(say) == [], say
    assert "please tell them" in say, say


@pytest.mark.parametrize("verdict", [True, None], ids=["passed-on", "under-way"])
def test_the_phone_says_it_told_the_family_when_the_callback_did(verdict):
    from cura.comms.responder import CuraResponder
    heard = []

    def cb(transcript):
        heard.append(transcript)
        return verdict
    say = CuraResponder(on_scam_report=cb).handle_speech(
        "Someone called asking for gift cards")["say"]
    assert heard, "the callback was never given the report"
    assert "let your family know" in say, say


@pytest.mark.parametrize("readme,opening,promise", [
    ("README.md", "**If someone asks you for money", "let your family know"),
    ("README.es.md", "**Si alguien le pide dinero", "le avisará a su familia"),
])
def test_the_readme_promises_the_family_only_if_production_tells_them(
        readme, opening, promise, tmp_path):
    """The README told an elder Cura would "let your family know" about a scam.
    Production wires no scam callback, so it did not."""
    lines = [l for l in (ROOT / readme).read_text().splitlines() if l.startswith(opening)]
    assert len(lines) == 1, f"{readme}: the scam paragraph moved; find it again"
    if _production_responder(tmp_path)._on_scam is None:
        assert promise not in lines[0], lines[0]


# --- Surfaces with no keypad: the MCP check-in and the console demo -----------

def _offers_a_key(text: str) -> bool:
    from tests.test_keypad_promises import _keys_named
    return bool(_keys_named(text)) or "press" in text.lower()


@pytest.mark.parametrize("time_of_day", ["morning", "evening"])
def test_the_mcp_checkin_offers_no_key_and_promises_no_call(time_of_day, sent, mcp_call):
    """Every cura_checkin script ended "press two and I'll call your family" on
    a server with no keypad that contacts nobody (batch 11 verifier, HIGH)."""
    for _ in range(6):        # the composer varies what it picks; ask several times
        payload = mcp_call("cura_checkin", {"time_of_day": time_of_day})
        lines = payload["all_messages"]
        claims = _payload_claims_alert(payload)
        assert not claims or sent, f"claimed {claims} with nothing sent: {lines}"
        offered = [l for l in lines if _offers_a_key(l)]
        assert not offered, f"a keypad-less server offers a key: {offered}"
        assert "911" in lines[-1], f"the script never says who to call for help: {lines}"


def _demo(monkeypatch, capsys) -> tuple[list[str], str]:
    monkeypatch.setattr(sys, "argv", ["cura", "console", "--name", "Margaret", "--demo"])
    from cura.__main__ import main
    main()
    out = capsys.readouterr().out
    said = [l.split("Cura:", 1)[1].strip() for l in out.splitlines() if "Cura:" in l]
    return said, out


def test_the_console_demo_promises_no_call_in_curas_voice(sent, monkeypatch, capsys):
    """`cura console --demo` printed "If you ever need help, press two and I'll
    call your family" for a profile with no phone and no contacts (MEDIUM)."""
    said, out = _demo(monkeypatch, capsys)
    assert said, out
    claims = [c for line in said for c in _text_claims_alert(line)]
    assert not claims or sent, f"claimed {claims} with nothing sent:\n{out}"
    offered = [l for l in said if _offers_a_key(l)]
    assert not offered, f"the console offers a key it cannot hear: {offered}"
    assert "This demo calls nobody" in out, out


def test_the_console_demo_still_tells_the_reader_about_two(monkeypatch, capsys):
    """The phone's help line is described, not dropped: a caregiver watching the
    demo learns that the real call tells her to press two."""
    _, out = _demo(monkeypatch, capsys)
    assert "press" in out.lower() and "two for her family" in out, out


# --- Crisis words before scam words, as the phone does ------------------------

#: Each holds a scam keyword ("in trouble", "irs", "arrest") and a crisis word.
BOTH_SAID = ["I fell and I am in trouble", "help, the IRS says they will arrest me"]


@pytest.mark.parametrize("said", BOTH_SAID)
def test_the_console_answers_distress_before_a_scam_word(said, sent, monkeypatch, capsys):
    out = _console(monkeypatch, capsys, said)
    assert "911" in out, f"a fall with a scam word got no 911:\n{out}"


@pytest.mark.parametrize("said", BOTH_SAID)
def test_the_mcp_server_answers_distress_before_a_scam_word(said, sent, mcp_call):
    payload = mcp_call("cura_ask", {"message": said})
    assert payload["status"] == "crisis", payload
    assert "911" in payload["response"], payload


# --- The caregiver summary -------------------------------------------------------

@pytest.mark.parametrize("fmt", ["detailed", "sms"])
def test_the_summary_says_no_scam_report_was_handled(fmt, sent, mcp_call):
    """The detailed summary said "flagged and handled". Nothing handles them."""
    mcp_call("cura_ask", {"message": "They want me to wire money today"})
    payload = mcp_call("cura_summary", {"format": fmt})
    assert payload["scam_alerts"] == 1, payload
    claims = _text_claims_alert(payload["formatted"])
    assert not claims or sent, f"claimed {claims} with nothing sent: {payload['formatted']}"
