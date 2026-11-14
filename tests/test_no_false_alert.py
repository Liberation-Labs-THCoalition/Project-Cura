"""Cura never says it is telling the family when nothing is sent (Lane 6, 2026-11-14).

The console and the MCP server both answered a frightened person with "I'm
alerting your family right now. Stay calm, stay where you are. You're not
alone." Neither can reach anyone: no phone line, no contacts, no escalation
callback. Nobody was alerted, and "stay where you are" told someone who had
fallen to wait for help that was not coming. The phone path closed this in
cura/comms/responder.py::_promise_help; these two surfaces were missed.

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

#: A first-person promise that someone is being, or will be, told or sent for.
_FIRST_PERSON = re.compile(
    r"\bI(?:'m| am|'ll| will)(?: going to)?\s+(?:\w+\s+)?"
    r"(?:alert|flag|let|tell|contact|notify|call|ring|reach|text|messag|send|pass|get)\w*\b"
    r"[^.!?]*\b(?:family|caregiver|daughter|son|someone|anyone|help)\b",
    re.IGNORECASE)
#: The same promise in the passive voice.
_PASSIVE = re.compile(
    r"\b(?:family|caregiver)\b[^.!?]*\b(?:is|are|has been|have been|will be)\s+"
    r"(?:being\s+)?(?:alerted|told|notified|contacted|called|flagged|informed)\b",
    re.IGNORECASE)
#: Words that only make sense if someone is on the way.
_ARRIVING = re.compile(
    r"help is (?:on the way|coming)|someone will (?:check on|come)|stay where you are",
    re.IGNORECASE)


def _text_claims_alert(text: str) -> list[str]:
    return [m.group(0) for p in (_FIRST_PERSON, _PASSIVE, _ARRIVING)
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
    return found


# The sentences these surfaces used to say, verbatim. The detector must catch
# every one of them, or a revert would pass the tests below.
HISTORIC_FALSE_SENTENCES = [
    "Margaret, I hear you. I'm alerting your family right now. "
    "Stay calm, stay where you are. You're not alone.",
]


@pytest.mark.parametrize("sentence", HISTORIC_FALSE_SENTENCES)
def test_the_detector_catches_each_sentence_that_was_said(sentence):
    assert _text_claims_alert(sentence), sentence


def test_the_detector_passes_the_sentence_that_replaced_them():
    from cura.console import CANNOT_REACH_ANYONE
    assert _text_claims_alert(CANNOT_REACH_ANYONE) == []


# --- Recording every way Cura can send ---------------------------------------

@pytest.fixture
def sent(monkeypatch):
    """Replace every primitive that reaches a person with a recorder."""
    log: list[str] = []
    from cura.comms import voice as voice_mod, ladder, escalation

    def _rec(label, result=None):
        def f(*a, **k):
            log.append(label)
            return result
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
    monkeypatch.setattr(escalation, "build_escalation", _rec("build_escalation"))
    monkeypatch.setattr(escalation, "build_ladder_escalation",
                        _rec("build_ladder_escalation"))
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
