"""Turning "about two o'clock" into a dose time, or refusing to.

The dose ledger answers correctly and NOTHING SUPPLIES IT -- the same shape
prn_status was in this morning. This is the supply, and it comes from the one
person in the house who can actually be a witness.

Thomas's framing, which decided the design: asking the caregiver "do you
remember how many times you gave her the pain med?" is not a logging chore. It
is an ordinary thing a friend asks inside a conversation that is worth having
anyway. The record is a by-product.

WHAT THE GUARD ACTUALLY NEEDS is not a count. prn_status answers "may I take
another one?" from TIME SINCE THE LAST DOSE, so "twice today" cannot answer it
and "about two o'clock" can. The count matters only for the daily ceiling.

REFUSING IS THE FEATURE. A wrong dose time is worse than no dose time: recorded
too late it permits a double dose, recorded too early it withholds a painkiller
from someone in pain. So this parses confidently or returns None, and None
routes to prn_status's UNKNOWN, which is already built to be a real answer
rather than a failure.
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone

#: Vague phrases people genuinely use. Deliberately NOT translated into times.
#: "After lunch" spans three hours, and a three-hour error is the whole interval
#: for a four-hourly opioid.
TOO_VAGUE = (
    "after lunch", "before lunch", "lunchtime", "after breakfast", "teatime",
    "after dinner", "before bed", "bedtime", "this morning", "this afternoon",
    "this evening", "earlier", "a while ago", "a bit ago", "some time ago",
    "not long ago", "recently", "a few hours", "couple of hours",
)

_CLOCK = re.compile(
    r"\b(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<mer>a\.?m\.?|p\.?m\.?|"
    r"in the morning|in the afternoon|in the evening|at night|tonight)?",
    re.I)

_AGO = re.compile(
    r"\b(?:(?P<num>\d+(?:\.\d+)?|an?|half an|a couple of|a few|"
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"fifteen|twenty|thirty|forty-five|forty five)\s+)?"
    r"(?P<unit>hours?|hrs?|minutes?|mins?)\s+ago\b", re.I)

_WORDS = {
    "an": 1, "a": 1, "half an": 0.5, "a couple of": 2, "a few": 3,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "fifteen": 15, "twenty": 20, "thirty": 30, "forty-five": 45,
    "forty five": 45,
}


#: Spelled-out hours. A caregiver says "two in the afternoon", not "14:00", and
#: a digits-only parser refuses the clearest answers he is likely to give.
_HOUR_WORDS = {
    "twelve": 12, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
}
_WORD_CLOCK = re.compile(
    r"\b(?:half past |quarter past |quarter to )?"
    r"(?P<w>" + "|".join(_HOUR_WORDS) + r")\b"
    r"(?:\s*(?P<mer>a\.?m\.?|p\.?m\.?|in the morning|in the afternoon|"
    r"in the evening|at night|last night|tonight))?", re.I)


def _digitise(s: str) -> str:
    """Rewrite a spelled-out hour into digits so one clock parser handles both.

    Only when a meridiem or time-of-day phrase follows, so a bare "two" stays
    ambiguous and is still refused -- "about two" must not silently become 2am.
    """
    m = _WORD_CLOCK.search(s)
    if not m or not m.group("mer"):
        return s
    hour = _HOUR_WORDS[m.group("w").lower()]
    minutes = 30 if "half past" in m.group(0).lower() else 0
    mer = m.group("mer")
    if mer in ("last night", "tonight"):
        mer = "at night"
    return s[:m.start()] + f"{hour}:{minutes:02d} {mer}" + s[m.end():]


def parse_dose_time(said: str, now: datetime,
                    tz=None) -> tuple[datetime | None, str]:
    """(when, why_not). `when` is None whenever the answer is not specific.

    Returns the reason too, so Cura can say what it could not use rather than
    silently discarding an answer the caregiver took trouble to give.
    """
    s = (said or "").strip().lower()
    if not s:
        return None, "nothing was said"

    if any(p in s for p in ("don't know", "do not know", "not sure",
                            "can't remember", "cannot remember", "no idea")):
        return None, "he said he could not remember"

    if any(p in s for p in ("never", "didn't", "did not", "none", "no she",
                            "hasn't", "has not")):
        return None, "no dose was given"

    s = _digitise(s)

    m = _AGO.search(s)
    if m:
        raw = (m.group("num") or "").strip().lower()
        if not raw:
            # "hours ago" with no number. DO NOT DEFAULT TO ONE. The first
            # version did, so "three hours ago" -- where "three" was not in the
            # alternatives and so did not match -- was silently recorded as ONE
            # hour ago. That is a two-hour error in the direction of TOO_SOON,
            # which withholds a painkiller from someone in pain. A silent wrong
            # answer, produced by the module written to refuse exactly those.
            return None, "no number was given, and I will not assume one"
        n = _WORDS.get(raw)
        if n is None:
            try:
                n = float(raw)
            except ValueError:
                return None, f"could not read {raw!r} as a number"
        unit = m.group("unit")
        delta = (timedelta(hours=n) if unit.startswith(("hour", "hr"))
                 else timedelta(minutes=n))
        return now - delta, ""

    # A vague phrase is only rejected if no clock time accompanies it. "About
    # two, after lunch" is usable; "after lunch" alone is not.
    clock = _CLOCK.search(s)
    has_clock = bool(clock and clock.group("h"))
    if not has_clock:
        for phrase in TOO_VAGUE:
            if phrase in s:
                return None, (f"{phrase!r} could be a three-hour window, and "
                              f"for a four-hourly medicine that is the whole "
                              f"interval")
        return None, "no time was given"

    hour = int(clock.group("h"))
    minute = int(clock.group("m") or 0)
    mer = (clock.group("mer") or "").replace(".", "").strip()
    if hour > 23 or minute > 59:
        return None, f"{said!r} is not a time of day"

    if mer.startswith("p") or "afternoon" in mer or "evening" in mer or "night" in mer:
        if hour != 12:
            hour += 12
    elif mer.startswith("a") or "morning" in mer:
        if hour == 12:
            hour = 0
    elif hour <= 12:
        # No meridiem at all. "About two" could be 2am or 2pm, and guessing
        # picks a twelve-hour error -- exactly the class that made
        # "1 tab at 7pm" resolve to morning.
        return None, (f"{hour} o'clock could be morning or afternoon, and "
                      f"guessing would be a twelve-hour error")

    local_now = now.astimezone(tz) if tz else now
    when = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if when > local_now:
        when -= timedelta(days=1)      # "at ten" said at 9am means last night
    return when.astimezone(timezone.utc), ""


def record_dose_answer(said: str, medication: str, ledger, now,
                       subject_id: str = "", tz=None) -> tuple[bool, str]:
    """Route a caregiver's answer into the ledger, or explain the refusal.

    The join. cura/pulse/dose_ledger.py answered correctly with nothing calling
    `record()` -- the same shape prn_status was in this morning, in the module
    written to fix it.

    Returns (recorded, what_to_say). Cura always says something, because a
    caregiver who answered and heard nothing back will reasonably assume it
    landed, and then trust a guard that has no idea.
    """
    from cura.pulse.dose_ledger import Source
    when, why = parse_dose_time(said, now, tz=tz)
    if when is None:
        if why == "no dose was given":
            return False, f"Good — I'll note that {medication} wasn't needed."
        return False, (
            f"I won't write that down as a time, because {why}. "
            f"I'd rather have no record than a wrong one — I'll keep asking.")
    ledger.record(medication, when, Source.CAREGIVER, subject_id=subject_id,
                  note=f"caregiver said: {said.strip()[:120]}")
    return True, f"Thank you — {medication} noted."
