"""Medication schedules — daily, weekly, and as-needed.

Cura began with two delivery slots, a morning check-in and an evening one, and
a medication was a name plus a free-text ``time`` resolved to one or both. That
model cannot express two things a real medicine cabinet contains, and it fails
differently for each.

WEEKLY. Alendronate on Sunday, methotrexate on Thursday. The old model had
nowhere to put the day, so a weekly drug either got announced every single day
or not at all. Announcing a weekly bisphosphonate daily is a real overdose
path, and it is the kind a confident prompt makes worse: someone who cannot
remember whether they took it will believe the reminder.

AS NEEDED (PRN). This is the one that matters, and it is not a scheduling
problem at all. **A PRN medication is a guard, not a reminder.** Cura must
never announce "time for your oxycodone" -- there is no such time. What Cura
must be able to answer is "can I take another one?", and that answer depends on
a single field the old model had nowhere to store: HOW LONG SINCE THE LAST
DOSE.

The safety rule that shapes this whole module:

    AN UNRECORDED DOSE IS INDISTINGUISHABLE FROM NO DOSE.

If Cura has no record of the last dose, that is not "it has been a long time".
She may have taken one twenty minutes ago and not said so, or a caregiver may
have given it. So the PRN check returns three states and never two: ALLOWED,
TOO_SOON, and UNKNOWN. UNKNOWN is never collapsed into ALLOWED. Getting this
wrong is a double dose of an opioid or a benzodiazepine in a household where
nobody can reliably remember the first one.

This is the same law the fail-state ledger runs on -- no observation, no claim
-- and the same one behind escalation returning None rather than a degraded
mode. A guard that cannot fail is indistinguishable from a guard that passed.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Schedule(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    PRN = "prn"
    UNKNOWN = "unknown"


class PRNVerdict(str, Enum):
    """Three states, deliberately. See the module docstring."""
    ALLOWED = "allowed"
    TOO_SOON = "too_soon"
    UNKNOWN = "unknown"       # no dose record -- defer to a human
    AT_DAILY_MAX = "at_daily_max"


# Dose quantities are stripped before any clock parsing. "1 tab at 7pm" used to
# resolve to MORNING, because the parser read the dose quantity as the hour --
# a twelve-hour dosing error from a perfectly ordinary label. FS-59d1316ced28.
_DOSE = re.compile(
    r"\b\d+(?:\.\d+)?\s*"
    r"(?:tabs?|tablets?|caps?|capsules?|pills?|mg|mcg|µg|ug|g|ml|cc|"
    r"units?|iu|drops?|puffs?|patch(?:es)?|sprays?|tsp|tbsp|lozenges?)\b",
    re.I)

_PRN = re.compile(
    r"\b(?:prn|as[- ]needed|as needed|if needed|when needed|when required|"
    r"as required|for pain|for breakthrough|rescue|only if|if she needs|"
    r"if he needs|when she needs|when he needs)\b", re.I)

_DAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}
_DAY_RE = re.compile(r"\b(" + "|".join(sorted(_DAYS, key=len, reverse=True)) + r")s?\b", re.I)
_WEEKLY_WORDS = re.compile(r"\b(?:weekly|once a week|every week|each week)\b", re.I)

_MORNING_WORDS = re.compile(r"\b(?:morning|breakfast|wake|waking|sunrise|am)\b", re.I)
_EVENING_WORDS = re.compile(r"\b(?:evening|night|bedtime|bed|dinner|supper|sunset|pm)\b", re.I)
_BOTH_WORDS = re.compile(r"\b(?:both|twice|two times|2x|bid)\b", re.I)

# "every 4 hours", "q4h", "every 4-6 hours", "every 6 hrs"
_INTERVAL = re.compile(
    r"\b(?:every|q)\s*(\d+(?:\.\d+)?)\s*(?:-\s*\d+(?:\.\d+)?\s*)?(?:h|hr|hrs|hours?)\b",
    re.I)
# "no more than 4 in 24 hours", "max 6 per day", "up to 4 daily", "4 max"
_MAX_DAY = re.compile(
    r"\b(?:no more than|not more than|max(?:imum)?(?: of)?|up to|limit(?: of)?)\s*"
    r"(\d+)\b|\b(\d+)\s*(?:doses? )?(?:max|maximum)\b", re.I)

_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b", re.I)



def _spoken_time(when: datetime, tz: tzinfo | None = None) -> str:
    """A clock time that cannot be misheard as the wrong half of the day.

    "1:30" is a coin flip to someone who cannot reconstruct the day, and the
    wrong half means a dose six hours early. "%-I:%M %p" would fix the
    ambiguity but reads as "P M" through text-to-speech, so this says it the
    way a person would.
    """
    if tz is not None:
        when = when.astimezone(tz)
    h = when.hour
    part = ("in the morning" if 5 <= h < 12 else
            "in the afternoon" if 12 <= h < 17 else
            "in the evening" if 17 <= h < 21 else
            "at night")
    return f"{when.strftime('%-I:%M')} {part}"


@dataclass
class Medication:
    """One medication, with a schedule Cura can actually act on."""
    name: str
    schedule: Schedule = Schedule.UNKNOWN
    slots: set[str] = field(default_factory=set)     # daily/weekly delivery
    days: set[int] = field(default_factory=set)      # weekly: 0=Mon .. 6=Sun
    hour: int | None = None                          # parsed clock hour, if any
    raw_timing: str = ""                             # exactly what was recorded

    # PRN only. None means "not stated", which is NOT the same as "no limit".
    min_interval_hours: float | None = None
    max_per_day: int | None = None

    @property
    def is_prn(self) -> bool:
        return self.schedule is Schedule.PRN

    @property
    def announceable(self) -> bool:
        """Whether Cura may ever say 'it is time for this'.

        PRN is never announceable. There is no time for an as-needed drug, and
        announcing one manufactures a dose that nobody asked for.
        """
        return self.schedule in (Schedule.DAILY, Schedule.WEEKLY) and bool(self.slots)


@dataclass
class PRNStatus:
    verdict: PRNVerdict
    reason: str                      # plain speech, safe to say aloud
    next_allowed: datetime | None = None
    doses_today: int = 0

    @property
    def safe_to_take(self) -> bool:
        """True ONLY for an affirmative record-backed allowance.

        UNKNOWN is false here on purpose. A caller that treats "I do not know"
        as "yes" is the double-dose bug this module exists to prevent.
        """
        return self.verdict is PRNVerdict.ALLOWED


def _slots_from_words(text: str) -> set[str]:
    if _BOTH_WORDS.search(text):
        return {"morning", "evening"}
    slots = set()
    if _MORNING_WORDS.search(text):
        slots.add("morning")
    if _EVENING_WORDS.search(text):
        slots.add("evening")
    return slots


def _hour_from_clock(text: str) -> int | None:
    """Resolve an hour, or None when the text is ambiguous.

    Candidates carrying a meridiem or a colon win outright. A bare number is
    accepted only when it is the sole candidate -- otherwise the string is
    ambiguous ("take 2 at 8") and ambiguity resolves to silence, not a guess.
    """
    cands = []
    for m in _CLOCK.finditer(text):
        hour = int(m.group(1))
        mer = (m.group(3) or "").replace(".", "").lower()
        explicit = bool(mer or m.group(2))
        if mer.startswith("p") and hour != 12:
            hour += 12
        elif mer.startswith("a") and hour == 12:
            hour = 0
        if 0 <= hour <= 23:
            cands.append((explicit, hour))

    explicit = [h for e, h in cands if e]
    if explicit:
        return explicit[0]
    bare = [h for e, h in cands if not e]
    return bare[0] if len(bare) == 1 else None


def parse_medication(med: dict[str, Any]) -> Medication:
    """Turn a recorded medication into something Cura can act on.

    Free text in, structure out: the wizard asks a person when they take it and
    a person answers like a person. "Sunday mornings", "every 4 hours if the
    pain is bad", "one at breakfast and one at bedtime".
    """
    name = str(med.get("name", "") or "").strip() or "?"
    raw = str(med.get("time", "") or "").strip()
    out = Medication(name=name, raw_timing=raw)
    if not raw:
        return out                                  # UNKNOWN -> silence

    # Dose quantities out of the way before anything reads a number as a clock.
    text = _DOSE.sub(" ", raw)

    # PRN is checked FIRST. "every 4 hours as needed" contains a number that
    # the clock parser would otherwise read as 4am, announcing a rescue opioid
    # at the morning check-in.
    if _PRN.search(text):
        out.schedule = Schedule.PRN
        iv = _INTERVAL.search(text)
        if iv:
            # "every 4-6 hours": the guard is the LOWER bound, since that is the
            # earliest the dose is permitted.
            out.min_interval_hours = float(iv.group(1))
        mx = _MAX_DAY.search(text)
        if mx:
            out.max_per_day = int(mx.group(1) or mx.group(2))
        return out

    days = {_DAYS[d.lower()] for d in _DAY_RE.findall(text)}
    if days or _WEEKLY_WORDS.search(text):
        out.schedule = Schedule.WEEKLY
        out.days = days
        out.slots = _slots_from_words(text)
        out.hour = _hour_from_clock(text)
        if out.hour is not None and not out.slots:
            out.slots = {"morning" if out.hour < 12 else "evening"}
        if not days:
            # "weekly" with no day named. We do not know WHICH day, and guessing
            # one is a dose on the wrong day every week.
            out.schedule = Schedule.UNKNOWN
            out.slots = set()
        return out


    slots = _slots_from_words(text)
    hour = _hour_from_clock(text)
    if not slots and hour is not None:
        slots = {"morning" if hour < 12 else "evening"}
    if slots:
        out.schedule = Schedule.DAILY
        out.slots = slots
        out.hour = hour
    return out


def due_today(med: Medication, when: datetime) -> bool:
    """Whether this medication belongs in today's check-ins at all."""
    if med.schedule is Schedule.DAILY:
        return True
    if med.schedule is Schedule.WEEKLY:
        return when.weekday() in med.days
    return False        # PRN and UNKNOWN are never scheduled


def slots_for(med: Medication, when: datetime) -> set[str]:
    """Which check-ins on THIS day should name this medication."""
    return set(med.slots) if due_today(med, when) else set()


def prn_status(
    med: Medication,
    now: datetime,
    doses: list[datetime] | None = None,
    ever_recorded: bool | None = None,
    tz: tzinfo | None = None,
) -> PRNStatus:
    """Answer 'can I take another one?' -- in three states, never two.

    Args:
        doses: recorded dose times. An EMPTY list is not evidence of no doses.
        ever_recorded: whether this household actually logs PRN doses. When
            False or None with no doses, the honest answer is UNKNOWN.
        tz: the household's timezone, used for every time SPOKEN ALOUD. Without
            it Cura reads back whatever zone the caller happened to pass, and a
            UTC timestamp told to someone in Wyoming is off by six hours -- in
            the direction of taking the next dose too early.

    The distinction between "no doses today" and "no records" is the entire
    safety property. A list that is empty because nobody ever writes to it
    looks exactly like a list that is empty because she has taken none.
    """
    if not med.is_prn:
        return PRNStatus(PRNVerdict.UNKNOWN,
                         f"{med.name} is not an as-needed medication.")

    doses = sorted(doses or [])
    if not doses:
        if ever_recorded:
            reason = (f"There's no record of {med.name} today, so it should be "
                      f"alright — but check with whoever's helping you.")
            return PRNStatus(PRNVerdict.ALLOWED, reason, doses_today=0)
        return PRNStatus(
            PRNVerdict.UNKNOWN,
            f"I don't have a record of when you last took {med.name}, so I "
            f"can't tell you it's safe. Please check with your caregiver.",
            doses_today=0)

    def _aware(d: datetime) -> datetime:
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

    now = _aware(now)
    doses = [_aware(d) for d in doses]
    last = doses[-1]
    today = [d for d in doses if (now - d) < timedelta(hours=24)]

    if med.max_per_day is not None and len(today) >= med.max_per_day:
        return PRNStatus(
            PRNVerdict.AT_DAILY_MAX,
            f"You've already had {len(today)} of your {med.name} in the last "
            f"day, which is the most you're meant to have. Please don't take "
            f"another without asking.",
            doses_today=len(today))

    if med.min_interval_hours is not None:
        nxt = last + timedelta(hours=med.min_interval_hours)
        if now < nxt:
            mins = max(1, int((nxt - now).total_seconds() // 60))
            hrs, rem = divmod(mins, 60)
            when = (f"{hrs} hour{'s' if hrs != 1 else ''}"
                    + (f" and {rem} minutes" if rem else "")) if hrs else f"{rem} minutes"
            return PRNStatus(
                PRNVerdict.TOO_SOON,
                f"It's a bit soon — you had one at "
                f"{_spoken_time(last, tz)}. Another would be alright in about "
                f"{when}, so around {_spoken_time(nxt, tz)}.",
                next_allowed=nxt, doses_today=len(today))
        return PRNStatus(
            PRNVerdict.ALLOWED,
            f"It's been long enough since your last {med.name}, so that's "
            f"alright.",
            doses_today=len(today))

    # A dose record exists, but no interval was ever recorded for this drug.
    return PRNStatus(
        PRNVerdict.UNKNOWN,
        f"I know you last had {med.name} at {_spoken_time(last, tz)}, but I "
        f"wasn't told how long to wait between doses. Please check before "
        f"taking another.",
        doses_today=len(today))


def needs_clarification(medications: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Medications a human must be asked about, with WHY.

    Silence is safe for dosing and unsafe for trust. A caregiver has to know
    which drugs Cura is not handling, or they will assume it is handling all of
    them. Returning the reason too means the question can be asked in plain
    words rather than as a list of failures.
    """
    out = []
    for raw in medications or []:
        m = parse_medication(raw)
        if m.schedule is Schedule.UNKNOWN:
            out.append((m.name, "I don't know when this one is taken."))
        elif m.schedule is Schedule.WEEKLY and not m.days:
            out.append((m.name, "I know this is weekly but not which day."))
        elif m.schedule is Schedule.WEEKLY and not m.slots:
            out.append((m.name,
                        "I know which day this one is, but not what time of "
                        "day."))
        elif m.is_prn and m.min_interval_hours is None:
            out.append((m.name,
                        "This one is as-needed, but I wasn't told how long to "
                        "wait between doses."))
    return out
