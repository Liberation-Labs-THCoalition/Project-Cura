"""Wiring the help request to someone who can actually help.

`CuraVoice.alert_caregiver` and `CuraVoice.crisis_alert` were fully implemented --
they call AND text every emergency contact -- and had no caller anywhere in
production. `CuraResponder` was constructed with `on_help_requested=None` at two
sites, so Cura answered "I fell and I can't get up" with "help is on the way" and
contacted nobody.

The reason it stayed broken is worth recording: `cura webhook` never took a config.
It knew a display name and nothing else, so it could not have escalated even if
someone had asked it to. The missing capability was upstream of the missing call,
and nothing in the code said so.

Two rules here, both learned the hard way:

  1. `build_escalation` returns None when it cannot escalate, and the caller must
     refuse to serve. A Cura that answers the phone without an escalation path is
     more dangerous than one that does not answer, because it stops her calling out.
  2. The callback is fire-and-forget from a sync context, but a failure to reach
     anyone is logged at ERROR and recorded. "We tried and could not" must never
     look the same as "we did".
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EscalationUnavailable(Exception):
    """Raised when Cura is asked to serve without a way to summon help."""



def _dialable(value) -> bool:
    """Whether this is a number a call can actually be placed to.

    Emptiness was the only test, so the bare string "+" passed — and "+" is
    exactly what norm_phone("") used to return, so a skipped question became an
    emergency contact Cura believed it could reach. A guard that accepts an
    undialable number is indistinguishable from a guard that passed.
    """
    digits = re.sub(r"\D", "", str(value or ""))
    return len(digits) >= 10 and not digits.lstrip("1").startswith(("0", "1"))


def escalation_readiness(profile) -> list[str]:
    """Reasons Cura cannot summon help. Empty list means it can.

    Checked explicitly rather than inferred, because every one of these has a
    plausible-looking config that produces silence at the worst moment.
    """
    problems: list[str] = []
    contacts = [c for c in (getattr(profile, "emergency_contacts", None) or [])
                if _dialable(c.get("phone", ""))]
    caregiver = getattr(profile, "primary_caregiver", None) or {}
    if not contacts and not _dialable(caregiver.get("phone", "")):
        problems.append(
            "no emergency contact has a phone number — nobody can be reached")
    if not _dialable(getattr(profile, "phone", "")):
        problems.append("the person Cura calls has no phone number Cura can dial")
    return problems


def build_escalation(voice, profile) -> Callable[[str], Any] | None:
    """Return an on_help_requested callback, or None if help cannot be summoned.

    None is a refusal, not a degraded mode. The caller must not serve on it.
    """
    problems = escalation_readiness(profile)
    if problems:
        for p in problems:
            logger.error("ESCALATION UNAVAILABLE: %s", p)
        return None

    def on_help_requested(context: str) -> None:
        logger.warning("ESCALATION FIRING: %s", context)
        try:
            coro = voice.crisis_alert(
                profile, crisis_type="help requested", details=context)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                results = asyncio.run(coro)
            else:
                loop.create_task(coro)
                results = None
            if results is not None:
                reached = [r for r in results if r]
                if not reached:
                    logger.error(
                        "ESCALATION REACHED NOBODY for %r. Every contact failed.",
                        context)
                else:
                    logger.warning("ESCALATION delivered to %d contact(s)",
                                   len(reached))
        except Exception:
            # Never let an escalation failure be swallowed. If this path is
            # silent, the household learns nothing and neither do we.
            logger.exception("ESCALATION FAILED for %r — nobody was contacted",
                             context)

    return on_help_requested

def build_ladder_escalation(voice, household, subject_id: str,
                            physician: dict | None = None,
                            monitoring_service: dict | None = None):
    """An on_help_requested callback that climbs the full ladder.

    The household-aware replacement for build_escalation. Same contract: returns
    None when help cannot be summoned, and None is a REFUSAL that the caller
    must not serve on.

    Wired here rather than left for later on purpose. cura/comms/ladder.py was
    written, tested and committed with no caller -- which is the defect this
    codebase produces more than any other, and I was about to produce it again
    in the module built to make sure somebody gets reached.
    """
    import asyncio

    problems = household.blocking_problems()
    if problems:
        for p in problems:
            logger.error("ESCALATION UNAVAILABLE: %s", p)
        return None

    def _sync(coro):
        """Run a coroutine and return its result, from sync or async context.

        The old escalation did `loop.create_task(coro)` and set results=None
        when a loop was already running, so in that path it NEVER LEARNED
        whether anyone was reached -- the check for "nobody answered" could not
        fire. Here the outcome is the whole point, so it is always awaited.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(asyncio.run, coro).result()

    def send_sms(number: str, message: str) -> bool:
        try:
            r = _sync(voice.send_sms(number, message))
        except Exception:
            logger.exception("SMS to %s failed", number)
            return False
        return bool(getattr(r, "sent", False) or getattr(r, "sid", ""))

    def place_call(number: str, message: str) -> bool:
        try:
            r = _sync(voice.call(to_number=number, messages=[message]))
        except Exception:
            logger.exception("call to %s failed", number)
            return False
        return bool(getattr(r, "answered", False))

    def on_help_requested(context: str) -> None:
        from cura.comms.ladder import climb
        logger.warning("ESCALATION FIRING: %s", context)
        try:
            trail = climb(household, subject_id, context,
                          send_sms=send_sms, place_call=place_call,
                          physician=physician,
                          monitoring_service=monitoring_service)
        except Exception:
            logger.exception(
                "ESCALATION RAISED for %r — treat as nobody reached", context)
            return
        if trail.reached_anyone:
            logger.warning("ESCALATION: %s", trail.summary())
        else:
            logger.critical("ESCALATION: %s", trail.summary())
        for r in trail.rungs:
            logger.info("  rung %-20s %s", r.rung.value,
                        "reached " + ", ".join(r.reached) if r.succeeded
                        else ("texted " + ", ".join(r.reached) if r.is_broadcast and r.reached
                              else ("no answer from " + ", ".join(r.failed) if r.failed
                                    else "not available: " + r.unavailable_because)))

    return on_help_requested
