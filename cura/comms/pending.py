"""Remembering what Cura just asked, so the answer has somewhere to go.

Cura asks "do you have grab bars in your bathroom, near the toilet and shower?"
She answers. `handle_speech` runs its keyword checks, matches nothing, and falls
through to "Thank you for sharing that with me. I enjoy our talks." The answer
is discarded, `record_concern` has never been called by anything, and
`get_summary()` reported "no concerns identified" every time -- with a test
asserting it did.

The missing piece is not a handler. It is MEMORY OF THE QUESTION: nothing
survives from the moment Cura asks to the moment she replies, so an answer
arrives with no idea what it is an answer to.

TWO RULES, and the first is the one that could hurt somebody.

**A pending question must never swallow an emergency.** If Cura asked about grab
bars and she says "I've fallen and I can't get up", that is not an answer about
grab bars. Help and scam checks run FIRST, always, and a pending question is
consulted only after they decline. Getting this backwards would route a fall
into a home-safety survey.

**A pending question expires.** An answer three turns later, or tomorrow, is not
an answer to what was asked. Better to lose an answer than to file an unrelated
sentence as one -- the whole point of asking is that the record means something.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

#: How long an answer can arrive and still be treated as an answer. One turn of
#: conversation, generously. Long pauses are common in the elderly -- Thomas
#: noted this specifically -- so this is not tight.
DEFAULT_TTL = timedelta(minutes=4)


@dataclass
class PendingQuestion:
    """What Cura just asked, and what to do with the reply."""
    topic: str                                   # "home_safety", "medication"
    asked_at: datetime
    handler: Callable[[str], Any] | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    ttl: timedelta = DEFAULT_TTL

    def expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        asked = self.asked_at
        if asked.tzinfo is None:
            asked = asked.replace(tzinfo=timezone.utc)
        return (now - asked) > self.ttl


def interpret_yes_no(transcript: str) -> bool | None:
    """Yes, no, or genuinely neither.

    None is a real answer and must not be coerced. "I don't know" and "what?"
    are not a no, and recording them as one would put a false fact in a safety
    record. Acquiescence bias runs the other way too: elderly respondents agree
    more readily than they disagree, so a bare "mm" is not a yes.
    """
    s = (transcript or "").strip().lower().rstrip(".!?")
    if not s:
        return None
    # Uncertainty is checked FIRST. "I don't know" starts with "i don't", which
    # is in the NO list, so ordering the other way recorded it as "no, there are
    # no grab bars" -- a false fact in a safety record, which is the specific
    # harm this function's docstring warns about. Caught by running it.
    UNSURE = ("don't know", "do not know", "not sure", "can't remember",
              "cannot remember", "no idea", "couldn't say", "maybe", "i think so",
              "sometimes", "what")
    if any(p in s for p in UNSURE):
        return None

    NO = ("no", "nope", "not really", "i don't", "i do not", "there isn't",
          "there is not", "we don't", "haven't got", "none", "never")
    YES = ("yes", "yeah", "yep", "we do", "i do", "there is", "there are",
           "we have", "i have", "got them", "uh huh")
    for phrase in NO:
        if s == phrase or s.startswith(phrase + " "):
            return False
    for phrase in YES:
        if s == phrase or s.startswith(phrase + " "):
            return True
    if any(p in s for p in NO):
        return False
    if any(p in s for p in YES):
        return True
    return None


# ---------------------------------------------------------------------------
# Cross-process persistence.
#
# `cura run` places the call that ASKS the question; `cura webhook` handles the
# reply. They are separate processes, so a PendingQuestion held in memory by one
# is invisible to the other -- and this whole mechanism would have been another
# correct half with nothing joined to it.
#
# A small file, same pattern as the dose ledger. Not elegant; honest about the
# two-process design rather than pretending it is one.
# ---------------------------------------------------------------------------

import json
import os
from pathlib import Path as _Path

PENDING_FILE = _Path.home() / ".cura" / "pending_question.json"


def save_pending(topic: str, asked_at: datetime, payload: dict | None = None,
                 path: _Path | None = None) -> None:
    p = _Path(path or PENDING_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "topic": topic,
        "asked_at": asked_at.isoformat(),
        "payload": payload or {},
    }))
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    os.replace(tmp, p)


def load_pending(path: _Path | None = None, now: datetime | None = None):
    """The stored question, or None if there is none or it has expired.

    Consumed on read: the file is removed, so one question yields at most one
    answer. A pending question that survived its answer would attach the NEXT
    thing she says to a survey she already completed.
    """
    p = _Path(path or PENDING_FILE)
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    try:
        p.unlink()
    except OSError:
        pass
    try:
        asked = datetime.fromisoformat(data["asked_at"])
    except (KeyError, ValueError):
        return None
    q = PendingQuestion(topic=data.get("topic", ""), asked_at=asked,
                        payload=data.get("payload", {}))
    return None if q.expired(now) else q
