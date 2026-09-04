"""Telling her the help button exists, without sounding like a recording.

Cura's <Gather>, its action URL, the escalation callback and the whole six-rung
ladder were built over four days -- and none of it could ever fire, because
**no scheduled call ever mentioned that a keypad existed.** Verified against
both composers: neither morning nor evening said "press" anywhere. Four halves
built, and the chain still dead, because the first link -- telling her -- was
never made.

THE DESIGN IS THOMAS'S, and it is better than "say the line every call":

    "It must be tongue in cheek after the first few days. 'And of course,
     because I'm mathematically compelled to say so...'  'Alright, we're
     wrapping up so you know what I have to say next...'  'Ok, good night, and
     -- wanna say it with me? If ever...'  'Want me to skip the emergency 2
     thing? Ok, goodnight!' and that sort of presence."

So: said EVERY call, because it is the only option that does not depend on her
remembering — repetition is a feature for this population, not a defect. But
the wording graduates from earnest to familiar to playful, so familiarity turns
into warmth instead of into a recording she stops hearing.

TWO RULES THE PLAYFULNESS MUST NOT BREAK.

**The digit is always spoken.** Every variant, including the jokes, contains the
actual number. "Want me to skip the emergency 2 thing?" still says two. The
humour wraps the content; it never replaces it.

**Never on inbound calls.** Someone who dialled Cura has already demonstrated
they can reach it. Reading them a menu is the IVR behaviour this is meant to
replace.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HelpPrompt:
    text: str
    stage: str          # earnest | familiar | playful


# Days of hearing it -> which register. Deliberately slow: a fortnight of plain
# statement before any joke, because the joke only reads as warmth once the
# information is genuinely old news.
EARNEST_UNTIL = 4
FAMILIAR_UNTIL = 14

_EARNEST = (
    "If you ever need help, press two and I'll call your family.",
    "One thing to remember: press two any time and I'll ring your family for you.",
    "And if you need anything at all, press two. That reaches your family.",
)

_FAMILIAR = (
    "You know the one — press two if you need your family.",
    "And the usual: two gets your family.",
    "Same as always, press two and I'll call your people.",
    "Before I go: two, if you need anyone.",
)

_PLAYFUL = (
    "And of course, because I'm mathematically compelled to say so — press two "
    "if you need your family.",
    "Alright, we're wrapping up, so you know what I have to say next. Two. "
    "Press two.",
    "Right then — wanna say it with me? If ever you need someone, press two.",
    "Want me to skip the press-two thing? No? Fair enough — press two if you "
    "need your family.",
    "And I'll spare you the speech, except the important half: two.",
)


def help_prompt(days_heard: int, *, inbound: bool = False,
                rotation: int = 0) -> HelpPrompt | None:
    """The line to close a check-in with, or None when it must not be said.

    Args:
        days_heard: how long she has been hearing it. Drives the register.
        inbound: True if SHE called US. Returns None — she has already proved
            she can reach Cura, and a menu is the thing this replaces.
        rotation: varies the wording within a register. Pass a stable per-call
            number (day of year, check-in count) rather than randomness, so
            `cura rehearse` shows what she will actually hear.

    Returns None ONLY for inbound. There is no other case where the line is
    dropped, because the alternative to saying it is a help button nobody knows
    about, which is what we had.
    """
    if inbound:
        return None
    if days_heard < EARNEST_UNTIL:
        pool, stage = _EARNEST, "earnest"
    elif days_heard < FAMILIAR_UNTIL:
        pool, stage = _FAMILIAR, "familiar"
    else:
        pool, stage = _PLAYFUL, "playful"
    return HelpPrompt(pool[rotation % len(pool)], stage)


def mentions_the_digit(text: str) -> bool:
    """Whether a line actually tells someone which key to press.

    The failure mode for a graduating script is a variant that gets funnier and
    stops being useful. This is asserted over every line in the tests, so a
    future addition cannot quietly drop the number.
    """
    lowered = text.lower()
    return "two" in lowered or "2" in lowered
