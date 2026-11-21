"""Every key a call names does what the call said, on the route the call posts to.

The evening call `cura run` places ends "If you ever need help, press two and
I'll call your family." Its keypresses go to /voice/evening-response, which read
2 as "all good" and said "Good. Sleep well tonight." with nothing sent. Two
existing tests locked in both halves (the evening call must say press two; 2 on
the evening route means goodnight), and each half passed on its own (batch 11
verifier, CRITICAL, 2026-11-14). Pressing 1 there threw away _promise_help's
answer and said "I'll let your family know" when nobody was reached (HIGH).

So these tests join the halves. They take the words from the real senders (the
scheduled jobs `cura run` builds, and CuraVoice's own scripts), post each key
those words name to the route the call posts to, through the signed webhook with
the responder built exactly as `cura webhook` builds it, and check what happened
(the ladder climbed or not) and what she heard (the TwiML).

The closed table of key lines below is this file's own (a test that reads its
expectations from the code under test agrees with any change). A line that
names a key and is not in the table fails the completeness test, so a new
key line cannot ship without someone saying what its key means.
"""
from __future__ import annotations

import json
import re
import sys
import types
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import pytest

TOKEN = "test-token-not-a-secret"

from cura.comms.voice import CuraVoice as _CuraVoice  # noqa: E402
#: Taken at import, before any fixture stubs them.
_REAL_SCRIPTS = {m: getattr(_CuraVoice, m)
                 for m in ("morning_checkin", "evening_checkin", "alert_caregiver")}
BASE = "https://cura.test"

# --- What each key line promises (this file's own table) ---------------------

#: Lines (or parts of lines) that name a key, and what each key must do there.
#: Meanings: help = a help request reaches the escalation callback;
#: med = the dose is recorded; chat / medication_question / scam_report = the
#: inbound menu's own actions.
KEY_LINES = {
    # The press-two line, every register (cura/pulse/help_prompt.py, Thomas's
    # design). Copied, not imported: if a variant changes, this table must.
    "If you ever need help, press two and I'll call your family.": {"2": "help"},
    "One thing to remember: press two any time and I'll ring your family for you.": {"2": "help"},
    "And if you need anything at all, press two. That reaches your family.": {"2": "help"},
    "You know the one — press two if you need your family.": {"2": "help"},
    "And the usual: two gets your family.": {"2": "help"},
    "Same as always, press two and I'll call your people.": {"2": "help"},
    "Before I go: two, if you need anyone.": {"2": "help"},
    "And of course, because I'm mathematically compelled to say so — press two "
    "if you need your family.": {"2": "help"},
    "Alright, we're wrapping up, so you know what I have to say next. Two. "
    "Press two.": {"2": "help"},
    "Right then — wanna say it with me? If ever you need someone, press two.": {"2": "help"},
    "Want me to skip the press-two thing? No? Fair enough — press two if you "
    "need your family.": {"2": "help"},
    "And I'll spare you the speech, except the important half: two.": {"2": "help"},
    # Replies that invite a key.
    "If you need help, press two.": {"2": "help"},
    "or press 4 if you need help right away.": {"4": "help"},
    # CuraVoice's own scripts.
    "Press 1 if you've taken your medications, or 2 if you need help.": {"1": "med", "2": "help"},
    "Is there anything you need before bed? If there is, press two, and I'll "
    "call your family.": {"2": "help"},
    # The inbound menu.
    "Press 1 if you'd like to chat.": {"1": "chat"},
    "Press 2 if you have a question about your medications.": {"2": "medication_question"},
    "Press 3 if you want to report something suspicious.": {"3": "scam_report"},
    "Press 4 if you need help.": {"4": "help"},
}

_WORD = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
         "six": "6", "seven": "7", "eight": "8", "nine": "9"}
_KEY = re.compile(r"\b(?:press(?:es|ed)?\s+(one|two|three|four|five|six|seven|"
                  r"eight|nine|[0-9])\b|(two)\b)", re.IGNORECASE)


def _keys_named(text: str) -> list[str]:
    """Every key the words tell her to press ("press two", "Press 4", and the
    press-two line's bare "two")."""
    out = []
    for m in _KEY.finditer(text):
        w = (m.group(1) or m.group(2)).lower()
        out.append(_WORD.get(w, w))
    return out


def _explained(text: str) -> dict[str, str]:
    """What the table says the keys in this text mean."""
    meaning: dict[str, str] = {}
    for line, keys in KEY_LINES.items():
        if line in text:
            for k, v in keys.items():
                assert meaning.get(k, v) == v, f"{text!r} gives {k} two meanings"
                meaning[k] = v
    return meaning


# --- What she must never be told after a help request -------------------------

#: Words only true if someone is on the way. A placed call is not that.
_ARRIVING = re.compile(
    r"help is (?:on (?:the|its) way|coming)|someone will (?:check on|come)|"
    r"stay where you are|on (?:their|her|his) way", re.IGNORECASE)
#: Words only true if the call stays open after this line.
_HOLDS_THE_LINE = re.compile(
    r"stay on the line|I'?(?:ll| will| am|'m going to) stay|let me repeat|"
    r"anything else\?|\bpress\b", re.IGNORECASE)


# --- Recording every way Cura can reach a person -------------------------------

class _Trail:
    def __init__(self, reached):
        self.reached_anyone = reached
        self.rungs = []

    def summary(self):
        return "reached" if self.reached_anyone else "NOBODY WAS REACHED."


@pytest.fixture
def ladder(monkeypatch):
    """ladder.climb replaced by a recorder whose verdict the test sets, and
    every CuraVoice primitive recorded, so nothing leaves the test."""
    from cura.comms import ladder as ladder_mod, voice as voice_mod
    state = {"reached": False, "climbs": [], "sent": []}

    def climb(household, subject_id, context, **kw):
        state["climbs"].append(context)
        return _Trail(state["reached"])
    monkeypatch.setattr(ladder_mod, "climb", climb)

    def _arec(label):
        async def f(*a, **k):
            state["sent"].append(label)
            return None
        return f
    for meth in ("send_sms", "alert_caregiver", "crisis_alert"):
        monkeypatch.setattr(voice_mod.CuraVoice, meth, _arec(meth))
    return state


def _config(tmp_path, days_heard=0):
    from tests.test_production_seam import _wizard_config
    p = _wizard_config(tmp_path)
    data = json.loads(p.read_text())
    data["started_on"] = (date.today() - timedelta(days=days_heard)).isoformat()
    data["public_url"] = BASE
    p.write_text(json.dumps(data))
    return p


def _app(cfg_path):
    from cura.__main__ import _build_responder
    from cura.comms.webhook import create_app
    return create_app(responder=_build_responder(str(cfg_path)),
                      elder_name="Margaret", auth_token=TOKEN, public_url=BASE)


def _post(app, path, form):
    from twilio.request_validator import RequestValidator
    sig = RequestValidator(TOKEN).compute_signature(BASE + path, form)
    r = app.test_client().post(path, data=form, headers={"X-Twilio-Signature": sig})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return ET.fromstring(r.get_data(as_text=True))


def _spoken(root):
    """[(text, inside_a_gather, gather_action)] for every <Say> in the reply."""
    out = []
    for child in root:
        if child.tag == "Gather":
            out += [(s.text or "", True, child.get("action")) for s in child.iter("Say")]
        elif child.tag == "Say":
            out.append((child.text or "", False, None))
    return out


def _scheduled_calls(tmp_path, monkeypatch, days_heard):
    """The calls `cura run` places, with the scheduler faked to run each job once
    and CuraVoice.call recorded: [(job, gather_response, gather_action, messages)]."""
    from cura.comms import voice as voice_mod
    from cura.comms.voice import CallResult
    from datetime import datetime, timezone
    placed = []

    async def call(self, to_number, messages, gather_response=False,
                   status_callback="", gather_action=""):
        placed.append((gather_response, gather_action, list(messages)))
        return CallResult(timestamp=datetime.now(timezone.utc),
                          to_number=to_number, answered=True)
    monkeypatch.setattr(voice_mod.CuraVoice, "call", call)
    monkeypatch.setattr("cura.__main__._weather", lambda p: None)

    jobs = []

    class _Scheduler:
        def add_job(self, fn, *a, **k):
            jobs.append((k.get("hour"), fn))

        def start(self):
            for _, fn in jobs:
                fn()
    blocking = types.ModuleType("apscheduler.schedulers.blocking")
    blocking.BlockingScheduler = _Scheduler
    for name, mod in (("apscheduler", types.ModuleType("apscheduler")),
                      ("apscheduler.schedulers", types.ModuleType("apscheduler.schedulers")),
                      ("apscheduler.schedulers.blocking", blocking)):
        monkeypatch.setitem(sys.modules, name, mod)

    from cura.__main__ import _run_scheduled
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = _config(tmp_path, days_heard)
    _run_scheduled(str(cfg), dry_run=False)
    assert len(placed) == 2, f"expected the morning and evening calls, got {placed}"
    return cfg, placed


# --- The calls `cura run` places ----------------------------------------------

DAYS = [0, 1, 2, 3, 4, 7, 10, 13, 14, 15, 16, 17, 18, 30]


@pytest.mark.parametrize("reached", [False, True], ids=["nobody-reached", "reached"])
@pytest.mark.parametrize("days_heard", DAYS)
def test_every_key_a_scheduled_call_names_does_what_it_said(
        days_heard, reached, tmp_path, monkeypatch, ladder):
    cfg, placed = _scheduled_calls(tmp_path, monkeypatch, days_heard)
    app = _app(cfg)
    ladder["reached"] = reached
    for gather, action, messages in placed:
        named = {k for m in messages for k in _keys_named(m)}
        assert named, f"a scheduled call names no key: {messages}"
        assert gather and action, f"a call names a key and nothing listens: {messages}"
        meaning = {}
        for m in messages:
            meaning.update(_explained(m))
        for key in named:
            assert key in meaning, f"no row in KEY_LINES says what {key} means in {messages}"
            ladder["climbs"].clear()
            said = _spoken(_post(app, action, {"Digits": key}))
            text = " ".join(t for t, _, _ in said)
            if meaning[key] == "help":
                assert ladder["climbs"], (
                    f"day {days_heard}: the call to {action} says {key} gets her "
                    f"family; pressing it reached no escalation. She heard: {text!r}")
                assert "sleep well" not in text.lower(), text
                assert not _ARRIVING.search(text), f"promised arrival: {text!r}"
                if not reached:
                    assert "nine one one" in text, (
                        f"nobody was reached and she was not told to call 911: {text!r}")
                    assert "let your family know" not in text, text


def test_the_evening_call_still_tells_her_about_two(tmp_path, monkeypatch, ladder):
    """The fix is in the handler, not by dropping Thomas's line from the call."""
    _, placed = _scheduled_calls(tmp_path, monkeypatch, 0)
    evening = [p for p in placed if p[1] == "/voice/evening-response"]
    assert evening, [p[1] for p in placed]
    assert "2" in _keys_named(evening[0][2][-1]), evening[0][2][-1]


# --- Every reply the routes give -----------------------------------------------

ROUTES = ["/voice/checkin-response", "/voice/evening-response", "/voice/inbound-response"]
KEYS = list("0123456789*#")
SPEECH = ["I fell and I can't get up", "help me", "Someone called asking for gift cards",
          "I had a nice walk", "I'm fine"]


def _replies(tmp_path, reached, ladder):
    app = _app(_config(tmp_path))
    ladder["reached"] = reached
    for path in ROUTES:
        for key in KEYS:
            ladder["climbs"].clear()
            said = _spoken(_post(app, path, {"Digits": key}))
            yield path, f"Digits={key}", said, bool(ladder["climbs"])
        for s in SPEECH:
            ladder["climbs"].clear()
            said = _spoken(_post(app, path, {"SpeechResult": s}))
            yield path, f"Speech={s!r}", said, bool(ladder["climbs"])
    for s in SPEECH:
        ladder["climbs"].clear()
        said = _spoken(_post(app, "/voice/inbound-chat", {"SpeechResult": s}))
        yield "/voice/inbound-chat", f"Speech={s!r}", said, bool(ladder["climbs"])


@pytest.mark.parametrize("reached", [False, True], ids=["nobody-reached", "reached"])
def test_a_reply_that_names_a_key_is_listening_for_it(reached, tmp_path, ladder):
    """And the key it names does what it says, on the route that will hear it."""
    replies = list(_replies(tmp_path, reached, ladder))
    app = _app(_config(tmp_path))
    checked = 0
    for path, what, said, _ in replies:
        for text, gathered, action in said:
            for key in _keys_named(text):
                assert gathered, f"{path} {what}: says press {key} and hangs up: {text!r}"
                meaning = _explained(text)
                assert key in meaning, f"{path} {what}: no KEY_LINES row for {text!r}"
                ladder["climbs"].clear()
                after = " ".join(t for t, _, _ in _spoken(_post(app, action, {"Digits": key})))
                if meaning[key] == "help":
                    assert ladder["climbs"], (
                        f"{path} {what}: '{text}' then {key} reached no escalation: {after!r}")
                checked += 1
    assert checked, "no reply named a key; the unknown-key reply should"


@pytest.mark.parametrize("reached", [False, True], ids=["nobody-reached", "reached"])
def test_a_reply_that_ends_the_call_promises_nothing_that_needs_the_line(
        reached, tmp_path, ladder):
    """"I'm going to stay on the line with you", "let me repeat that", "Is there
    anything else?" were each said, and then the call ended."""
    for path, what, said, _ in _replies(tmp_path, reached, ladder):
        for text, gathered, _ in said:
            if not gathered:
                assert not _HOLDS_THE_LINE.search(text), (
                    f"{path} {what}: the call ends after {text!r}")


@pytest.mark.parametrize("reached", [False, True], ids=["nobody-reached", "reached"])
def test_after_a_help_request_she_hears_only_what_was_done(reached, tmp_path, ladder):
    from tests.test_no_false_alert import _text_claims_alert
    helped = 0
    for path, what, said, climbed in _replies(tmp_path, reached, ladder):
        if not climbed:
            continue
        helped += 1
        text = " ".join(t for t, _, _ in said)
        assert not _ARRIVING.search(text), f"{path} {what}: promised arrival: {text!r}"
        if not reached:
            assert "nine one one" in text, f"{path} {what}: nobody reached, no 911: {text!r}"
            assert _text_claims_alert(text) == [], f"{path} {what}: {text!r}"
    # 2 on checkin and evening, 1 on evening, 4 inbound, and two help phrases on
    # each of the four routes.
    assert helped >= 4 + 8, helped


def test_every_line_that_names_a_key_has_a_row(tmp_path, ladder, monkeypatch):
    """Completeness: the table above covers every key line Cura can say."""
    lines = set()
    for days in DAYS:
        _, placed = _scheduled_calls(tmp_path / f"d{days}", monkeypatch, days)
        lines |= {m for _, _, msgs in placed for m in msgs}
    for reached in (False, True):
        lines |= {t for _, _, said, _ in _replies(tmp_path, reached, ladder) for t, _, _ in said}
    from cura.comms.responder import CuraResponder
    lines.add(CuraResponder().build_inbound_menu())
    missing = [l for l in lines if _keys_named(l) and set(_keys_named(l)) - set(_explained(l))]
    assert not missing, f"key lines with no row in KEY_LINES: {missing}"


# --- CuraVoice's own scripts ---------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("script", ["morning_checkin", "evening_checkin", "alert_caregiver"])
async def test_a_scripted_call_posts_each_key_to_a_route_that_honours_it(
        script, tmp_path, ladder, monkeypatch):
    """Not on `cura run`'s path, but callable. evening_checkin said "Press 1 for
    yes, or 2 for no" and posted to the morning route, where 1 is a dose and 2 is
    the family; alert_caregiver asked the caregiver to press 1 on that same route."""
    from cura.comms import voice as voice_mod
    from cura.comms.voice import CallResult, CuraVoice
    from cura.pulse.eldercare_pulse import ElderProfile
    from datetime import datetime, timezone
    placed = []

    async def call(self, to_number, messages, gather_response=False,
                   status_callback="", gather_action=""):
        placed.append((gather_response, gather_action, list(messages)))
        return CallResult(timestamp=datetime.now(timezone.utc),
                          to_number=to_number, answered=True)
    monkeypatch.setattr(voice_mod.CuraVoice, "call", call)
    profile = ElderProfile(
        name="Margaret Chen", preferred_name="Margaret", phone="+13075550134",
        medications=[{"name": "Lisinopril", "time": "morning"}],
        emergency_contacts=[{"name": "Ray", "phone": "+13075550199"}],
        primary_caregiver={"name": "Ray", "phone": "+13075550199"})
    # The ladder fixture stubs these; this test needs the real scripts.
    for meth, real in _REAL_SCRIPTS.items():
        monkeypatch.setattr(voice_mod.CuraVoice, meth, real)
    monkeypatch.setattr(voice_mod.CuraVoice, "call", call)
    voice = CuraVoice(dry_run=True)
    if script == "alert_caregiver":
        await voice.alert_caregiver(profile, "missed_checkin", "she did not answer")
    else:
        await getattr(voice, script)(profile)
    assert placed
    app = _app(_config(tmp_path))
    for gather, action, messages in placed:
        named = [k for m in messages for k in _keys_named(m)]
        if not named:
            continue
        assert gather and action, f"{script} names a key and nothing listens: {messages}"
        meaning = {}
        for m in messages:
            meaning.update(_explained(m))
        for key in named:
            assert key in meaning, f"{script}: no KEY_LINES row for key {key}: {messages}"
            ladder["climbs"].clear()
            _post(app, action, {"Digits": key})
            assert bool(ladder["climbs"]) is (meaning[key] == "help"), (
                f"{script} says {key} means {meaning[key]}; on {action} it "
                f"{'did not reach' if not ladder['climbs'] else 'reached'} the escalation")


# --- The README says what the keys do ------------------------------------------

@pytest.mark.parametrize("readme,one,two,noted", [
    ("README.md", "- **Presses 1**", "- **Presses 2**", "notes she took"),
    ("README.es.md", "- **Presiona 1**", "- **Presiona 2**", "anota que tomó"),
])
def test_the_readme_says_what_the_keys_do(readme, one, two, noted, tmp_path):
    """README said "Presses 1 -> Cura notes she took her medications" (production
    wires no medication callback) and "Presses 2 -> Cura alerts the family
    immediately" (true on the morning call only, until this lane)."""
    from pathlib import Path
    from cura.__main__ import _build_responder
    text = (Path(__file__).resolve().parents[1] / readme).read_text()
    rows = {k: [l for l in text.splitlines() if l.startswith(k)] for k in (one, two)}
    assert all(len(v) == 1 for v in rows.values()), f"{readme}: the keypad rows moved: {rows}"
    if _build_responder(str(_config(tmp_path)))._on_med is None:
        assert noted not in rows[one][0], rows[one][0]
    assert ("evening" in rows[two][0]) or ("noche" in rows[two][0]), rows[two][0]
