"""FS-fcea817cb681 — webhook._say() interpolates text into TwiML unescaped.

    def _say(text):
        return f'<Say voice="{_voice}" rate="{_rate}">{text}</Say>'

No xml.sax.saxutils.escape. The elder's name flows through _elder_name ->
build_inbound_greeting() -> _gather() -> _say(), so a name with an ampersand in
it -- "Tom & Barbara", "Mom & Dad's house", the kind of thing a caregiver types
into "What does she like to be called?" -- produces XML Twilio will not parse.

Observed on this revision:

    <Say voice="Polly.Joanna" rate="slow">Tom & Barbara said <hello></Say>
    xml.etree.ElementTree: not well-formed (invalid token): line 1, column 91

What reaches the household: Twilio's response to malformed TwiML is to hang up.
She calls Cura, it answers, and there is silence. No error is raised on Cura's
side -- the route returns 200 with a broken body -- so nothing in the logs says
the call failed, and the caregiver has no idea the inbound line is dead.

This is the same class as FS-2b702d758df4 (voice.py::_build_twiml) at a second
locus. Fixing one does not fix the other; webhook.py builds its own TwiML.

RED = _say()/_gather() output is not well-formed XML for a plausible name.
"""
import pathlib
import sys
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from cura.comms import webhook

NAMES = ["Tom & Barbara", "Mom & Dad", "Bea <the neighbour>", 'Peg "Pegs"']


@pytest.mark.parametrize("text", NAMES)
def test_say_produces_well_formed_twiml(text):
    doc = webhook._twiml(webhook._say(f"Hello, {text}. It's Cura."))
    try:
        ET.fromstring(doc)
    except ET.ParseError as exc:
        pytest.fail(
            f"{text!r} produced TwiML Twilio cannot parse ({exc}). Twilio hangs "
            f"up on unparseable TwiML and the route still returns 200, so the "
            f"call silently fails and nothing reports it.\n  {doc}"
        )


@pytest.mark.parametrize("text", NAMES)
def test_gather_produces_well_formed_twiml(text):
    doc = webhook._twiml(webhook._gather(f"Hello, {text}.", "/voice/inbound-response"))
    try:
        ET.fromstring(doc)
    except ET.ParseError as exc:
        pytest.fail(f"{text!r} broke the inbound greeting TwiML ({exc}).\n  {doc}")
