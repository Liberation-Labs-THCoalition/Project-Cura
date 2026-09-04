"""The escalation ladder — bounded, enumerated, and it says when it ran out.

Escalation was one attempt at the profile's contacts. If nobody answered it
logged a line and stopped. For the household this is being built for, that is
the most likely bad outcome rather than an edge case:

    A man in his seventies is the SOLE caregiver for his wife, who has
    late-stage dementia and cannot answer a phone. If HE falls, she cannot call
    for help and cannot report that he is down. Cura's only contact is the
    person who is down.

So the ladder needs a rung outside that house, and it needs to know when it has
run out of rungs.

TWO RULES, both learned the hard way in this codebase.

**Bounded and enumerated.** Every rung is named in advance and the ladder ends.
An escalation that improvises until it "succeeds" is the thing that would do
something unforgivable at three in the morning. There is no rung that is not on
this list, and the list is data, not judgement.

**A rung nobody could attempt is not a rung that failed.** If no physician is
configured, that is NOT "the physician did not answer" — it is a rung that was
never there. Collapsing the two produces a trail that reads like six attempts
when there were two, which is how a family concludes everything possible was
tried. Same law as the guardian's "All clear" and prn_status's UNKNOWN: not
looking is not the same as looking and finding nothing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Sequence

logger = logging.getLogger(__name__)


class Rung(str, Enum):
    """Every rung, in order. Nothing is attempted that is not here.

    SMS_EVERYONE is first and simultaneous because it is the only step that
    costs nothing to fan out. A sequential ladder spends its first ninety
    seconds ringing one phone; a text reaches every phone at once and may be
    read by someone already awake.
    """
    SMS_EVERYONE = "sms_everyone"
    CALL_CAREGIVERS = "call_caregivers"
    CALL_HOUSEHOLD = "call_household"
    CALL_OUTSIDE = "call_outside"
    CALL_PHYSICIAN = "call_physician"
    MONITORING_SERVICE = "monitoring_service"


LADDER: tuple[Rung, ...] = (
    Rung.SMS_EVERYONE,
    Rung.CALL_CAREGIVERS,
    Rung.CALL_HOUSEHOLD,
    Rung.CALL_OUTSIDE,
    Rung.CALL_PHYSICIAN,
    Rung.MONITORING_SERVICE,
)


@dataclass
class RungResult:
    """What happened at one rung. `attempted` is the load-bearing field."""
    rung: Rung
    attempted: bool
    reached: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    unavailable_because: str = ""
    is_broadcast: bool = False       # delivered, but nobody answered anything

    @property
    def succeeded(self) -> bool:
        """A DELIVERED TEXT IS NOT A PERSON.

        I wrote a comment on the SMS rung saying exactly this, and then let SMS
        success count toward reached_anyone anyway -- so the ladder reported
        "Reached Thomas" when all that happened was a text left on a phone at
        3am. That is the false success this whole module exists to prevent,
        written by me, fifteen minutes after warning about it.

        Only an answered call counts. The text still goes, and is still
        recorded, because it may be the thing that actually wakes someone.
        """
        return bool(self.reached) and not self.is_broadcast


@dataclass
class EscalationTrail:
    """The whole attempt, in order, with nothing collapsed."""
    context: str
    rungs: list[RungResult] = field(default_factory=list)

    @property
    def reached_anyone(self) -> bool:
        return any(r.succeeded for r in self.rungs)

    @property
    def rungs_attempted(self) -> int:
        return sum(1 for r in self.rungs if r.attempted)

    @property
    def rungs_unavailable(self) -> int:
        return sum(1 for r in self.rungs if not r.attempted)

    def summary(self) -> str:
        """Plain words, for a caregiver reading this later.

        States attempted and unavailable separately, always. "Tried six things"
        when four of them did not exist is the sentence that makes a family
        believe everything possible was done.
        """
        if self.reached_anyone:
            seen, who = set(), []
            for r in self.rungs:
                if not r.succeeded:
                    continue
                for n in r.reached:
                    if n not in seen:
                        seen.add(n); who.append(n)
            return (f"Reached {', '.join(who)} after "
                    f"{self.rungs_attempted} attempt"
                    f"{'s' if self.rungs_attempted != 1 else ''}.")
        texted = [n for r in self.rungs if r.is_broadcast for n in r.reached]
        parts = [f"NOBODY WAS REACHED. {self.rungs_attempted} rung"
                 f"{'s' if self.rungs_attempted != 1 else ''} attempted"]
        if texted:
            parts.append(
                f"{len(texted)} text{'s' if len(texted) != 1 else ''} delivered "
                f"({', '.join(texted)}) but nobody answered a call")
        if self.rungs_unavailable:
            missing = ", ".join(r.rung.value for r in self.rungs if not r.attempted)
            parts.append(
                f"{self.rungs_unavailable} never existed to try ({missing})")
        return "; ".join(parts) + "."


def climb(
    household,
    subject_id: str,
    context: str,
    *,
    send_sms: Callable[[str, str], bool],
    place_call: Callable[[str, str], bool],
    physician: dict | None = None,
    monitoring_service: dict | None = None,
    raised_by: str | None = None,
) -> EscalationTrail:
    """Work down the ladder until somebody is reached, or until it runs out.

    Args:
        household: a cura.household.Household.
        subject_id: who needs help. Never contacted about their own emergency.
        send_sms / place_call: (number, message) -> reached?  Injected so this
            is testable without Twilio, and so a failure to *send* is
            distinguishable from a failure to *answer*.
        raised_by: who raised the alarm, if not the subject. Also excluded --
            calling the person already on the line wastes the rung.

    Stops at the first rung that reaches someone. Every rung below that is
    recorded as not attempted, so the trail never implies more effort than was
    made.
    """
    from cura.household import Purpose, may_call

    trail = EscalationTrail(context=context)
    exclude = {subject_id} | ({raised_by} if raised_by else set())

    reachable = household.callable_for(Purpose.HELP, excluding=exclude)
    caregivers = {m.member_id for m in household.caregivers_of(subject_id)}
    subject = household.members.get(subject_id)
    who = subject.display_name if subject else subject_id
    message = f"{who} needs help. {context}"

    def _finish(remaining: Sequence[Rung]) -> EscalationTrail:
        for r in remaining:
            trail.rungs.append(RungResult(
                rung=r, attempted=False,
                unavailable_because="someone was already reached"))
        return trail

    for i, rung in enumerate(LADDER):
        rest = LADDER[i + 1:]

        if rung is Rung.SMS_EVERYONE:
            targets = [m for m in reachable if m.phone]
            if not targets:
                trail.rungs.append(RungResult(
                    rung, False,
                    unavailable_because="nobody in the household can be texted"))
                continue
            reached, failed = [], []
            # Simultaneous in intent: every target is tried, and one failure
            # does not stop the rest. A sequential text loop that aborts on the
            # first error reaches nobody because of one bad number.
            for m in targets:
                try:
                    ok = send_sms(m.phone, message)
                except Exception:
                    logger.exception("SMS to %s raised", m.display_name)
                    ok = False
                (reached if ok else failed).append(m.display_name)
            trail.rungs.append(RungResult(rung, True, reached, failed,
                                          is_broadcast=True))
            # An SMS being *delivered* is not somebody *answering*. Texting is
            # a broadcast, not a rung that can end the climb -- keep going.
            continue

        if rung is Rung.CALL_CAREGIVERS:
            targets = [m for m in reachable if m.member_id in caregivers]
            unavailable = "this person has no caregiver who can be called"
        elif rung is Rung.CALL_HOUSEHOLD:
            targets = [m for m in reachable if m.member_id not in caregivers]
            unavailable = "nobody else in the household can be called"
        elif rung is Rung.CALL_OUTSIDE:
            targets = [m for m in reachable
                       if not household.is_cared_for(m.member_id)
                       and m.member_id not in caregivers]
            unavailable = ("there is nobody outside this household to call — "
                           "if the caregiver is the one in trouble, this is "
                           "where the ladder ends")
        elif rung is Rung.CALL_PHYSICIAN:
            targets = []
            unavailable = "no physician is on file"
            if physician and physician.get("phone"):
                trail.rungs.append(_dial_group(
                    rung, [(physician.get("name", "the physician"),
                            physician["phone"])], message, place_call))
                if trail.rungs[-1].succeeded:
                    return _finish(rest)
                continue
        elif rung is Rung.MONITORING_SERVICE:
            targets = []
            unavailable = "no monitoring service is configured"
            if monitoring_service and monitoring_service.get("phone"):
                trail.rungs.append(_dial_group(
                    rung, [(monitoring_service.get("name", "the monitoring service"),
                            monitoring_service["phone"])], message, place_call))
                if trail.rungs[-1].succeeded:
                    return _finish(rest)
                continue
        else:
            continue

        if not targets:
            trail.rungs.append(RungResult(rung, False, unavailable_because=unavailable))
            continue

        trail.rungs.append(_dial_group(
            rung, [(m.display_name, m.phone) for m in targets], message, place_call))
        if trail.rungs[-1].succeeded:
            return _finish(rest)

    if not trail.reached_anyone:
        # This must be impossible to miss. It is the outcome the whole system
        # exists to prevent, and the one a silent log would hide.
        logger.critical("ESCALATION EXHAUSTED — %s", trail.summary())
        logger.critical("  context: %s", context)
    return trail


def _dial_group(rung: Rung, targets, message: str,
                place_call: Callable[[str, str], bool]) -> RungResult:
    reached, failed = [], []
    for name, number in targets:
        try:
            ok = place_call(number, message)
        except Exception:
            logger.exception("call to %s raised", name)
            ok = False
        (reached if ok else failed).append(name)
        if ok:
            break        # someone answered; stop dialling this rung
    return RungResult(rung, True, reached, failed)
