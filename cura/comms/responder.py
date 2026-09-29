"""Responder — Cura's ears. Handles what Margaret says back.

When Cura calls Margaret and she presses a button or speaks,
Twilio sends a webhook to this handler. When Margaret calls
Cura's number, this picks up and has a conversation.

Two modes:
  1. Callback — processes responses to scheduled check-ins
     (DTMF: press 1 = took meds, press 2 = need help)
  2. Inbound — Margaret called Cura to chat, ask a question,
     or report something suspicious

The responder feeds everything back into the system:
  - Medication confirmations → pulse config
  - Help requests → caregiver alerts
  - Speech content → scam shield analysis
  - Inbound calls → conversation mode
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CuraResponder:
    """Process responses from elders during and after calls.

    Args:
        on_medication_confirmed: Called when elder confirms meds
        on_help_requested: Called when elder needs help
        on_scam_report: Called when elder reports suspicious contact
        on_speech: Called with transcribed speech for analysis
    """

    def __init__(
        self,
        on_medication_confirmed: Callable[[], Any] | None = None,
        on_help_requested: Callable[[str], Any] | None = None,
        on_scam_report: Callable[[str], Any] | None = None,
        on_speech: Callable[[str], Any] | None = None,
    ) -> None:
        self._on_med = on_medication_confirmed
        self._on_help = on_help_requested
        self._on_scam = on_scam_report
        self._on_speech = on_speech
        self._response_log: list[dict[str, Any]] = []
        self._pending = None      # cura.comms.pending.PendingQuestion | None


    def expect_answer(self, topic: str, handler=None, **payload) -> None:
        """Record that Cura just asked something, so the reply has a home.

        Nothing survived from the moment Cura asked to the moment she replied,
        so an answer arrived with no idea what it answered -- which is why
        record_concern has never been called and the home-safety assessment
        reported "no concerns identified" every time.
        """
        from datetime import datetime, timezone
        from cura.comms.pending import PendingQuestion, save_pending
        now = datetime.now(timezone.utc)
        self._pending = PendingQuestion(
            topic=topic, asked_at=now, handler=handler, payload=dict(payload))
        # Persist: the process that ASKS is `cura run`, the process that hears
        # the answer is `cura webhook`. In-memory only would have made this
        # another correct half with nothing joined to it.
        try:
            save_pending(topic, now, dict(payload))
        except OSError:
            logger.warning("could not persist the pending question (%s)", topic)

    def _take_pending(self):
        """The live question, if there is one and it has not expired."""
        from cura.comms.pending import load_pending
        p, self._pending = self._pending, None
        if p is None:
            # Asked by the other process. Read it from disk instead.
            p = load_pending()
        if p is None or p.expired():
            return None
        return p

    def _promise_help(self, context: str, when_reachable: str) -> str:
        """Return what Cura may truthfully say about getting help.

        Cura previously said "I'm alerting your family right now. Help is on the
        way." whenever help was requested -- including when `on_help_requested`
        was None, which is how it is constructed at __main__.py:106 and
        webhook.py:189. Nobody was alerted. A woman with dementia who has fallen
        was told help was coming, and then nothing happened.

        That is the most dangerous thing this system can do. It is worse than
        silence, because silence leaves her calling out; a false assurance stops
        her calling out.

        So the promise is conditional on there being someone to call. Each caller
        passes its own warm wording for the reachable case -- these differ by
        situation and are worth keeping; an earlier version of this guard
        flattened them into one line and lost "You're not alone", which is the
        warmest thing Cura says to a frightened person.
        """
        if self._on_help:
            # The callback's own verdict decides. True: someone was reached.
            # None: it started and the outcome is not known yet (an alert
            # scheduled on a running loop); "contacting" is still true then.
            # False, or an exception: nobody was reached, and Cura says so.
            try:
                outcome = self._on_help(context)
            except Exception:
                logger.exception("ESCALATION RAISED (%s). Nobody can be assumed "
                                 "reached.", context)
                outcome = False
            if outcome is not False:
                return when_reachable
            logger.critical("ESCALATION REACHED NOBODY (%s). Cura will not "
                            "promise help.", context)
        else:
            logger.error(
                "ESCALATION REQUESTED WITH NO CALLBACK WIRED (%s). Nobody was "
                "contacted. Cura must not be placing live calls in this state.",
                context,
            )
        return ("I can't reach anyone for you myself right now. "
                "If you need help, please hang up and dial nine one one. "
                "I'm going to stay on the line with you.")

    def handle_dtmf(self, digit: str, call_context: str = "checkin") -> dict[str, str]:
        """Handle a keypad press during a call.

        Returns a dict with 'action' and 'twiml_response' (what to say next).
        """
        now = datetime.now(timezone.utc)
        self._response_log.append({
            "timestamp": now, "type": "dtmf", "digit": digit, "context": call_context,
        })

        if call_context == "checkin":
            if digit == "1":
                if self._on_med:
                    self._on_med()
                return {
                    "action": "medication_confirmed",
                    "say": "Thank you. I'm glad you're staying on top of your medications. "
                           "Have a wonderful day.",
                }
            elif digit == "2":
                return {
                    "action": "help_requested",
                    "say": self._promise_help(
                        "Elder pressed 2 — needs help",
                        "I'm letting your family know right now. "
                        "Stay where you are and someone will check on you soon. "
                        "You're not alone."),
                }
            elif digit == "9":
                return {
                    "action": "repeat",
                    "say": "Of course, let me repeat that.",
                }

        if call_context == "evening":
            if digit == "1":
                self._promise_help("Elder needs something before bed",
                                   "I'll let your family know.")
                return {
                    "action": "help_requested",
                    "say": "I'll let your family know. Is there anything else?",
                }
            elif digit == "2":
                return {
                    "action": "all_good",
                    "say": "Good. Sleep well tonight. I'll talk to you in the morning.",
                }

        return {
            "action": "unknown",
            "say": "I didn't understand that. Press 1 for yes or 2 for no. "
                   "Press 9 to hear the message again.",
        }

    def handle_speech(self, transcript: str, call_context: str = "checkin") -> dict[str, str]:
        """Handle transcribed speech from the elder.

        Runs the transcript through scam analysis and generates
        an appropriate response.
        """
        now = datetime.now(timezone.utc)
        self._response_log.append({
            "timestamp": now, "type": "speech", "transcript": transcript,
            "context": call_context,
        })

        if self._on_speech:
            self._on_speech(transcript)

        lower = transcript.lower()

        if any(w in lower for w in ["help", "emergency", "fall", "fell", "hurt", "pain"]):
            return {
                "action": "help_requested",
                "say": self._promise_help(
                    f"Elder said: {transcript[:200]}",
                    "I'm alerting your family right now. Stay calm, stay safe. "
                    "Help is on the way."),
            }

        if any(w in lower for w in [
            "someone called", "asked for money", "gift card", "wire",
            "scam", "suspicious", "weird call", "strange email",
        ]):
            if self._on_scam:
                self._on_scam(transcript)
            return {
                "action": "scam_report",
                "say": "Thank you for telling me about that. You did the right thing. "
                       "I'm going to let your family know so they can help look into it. "
                       "Remember, it's never wrong to check with someone you trust.",
            }

        # ONLY after help and scam have declined. A pending question must never
        # swallow an emergency: if Cura asked about grab bars and she says "I've
        # fallen and I can't get up", that is not an answer about grab bars.
        pending = self._take_pending()
        if pending is not None:
            from cura.comms.pending import interpret_yes_no
            answer = interpret_yes_no(transcript)
            if pending.handler is not None:
                try:
                    pending.handler(answer, transcript)
                except Exception:
                    logger.exception("pending-question handler raised (%s)",
                                     pending.topic)
            if answer is None:
                # Not coerced. "I don't know" is not a no, and recording it as
                # one puts a false fact in a safety record.
                return {"action": f"{pending.topic}_unclear",
                        "say": "That's alright — I'll ask again another time."}
            return {"action": f"{pending.topic}_answered",
                    "say": ("Thank you, that's good to know."
                            if answer else
                            "Thank you for telling me. I'll make a note of "
                            "that for your family.")}

        return {
            "action": "conversation",
            "say": "Thank you for sharing that with me. I enjoy our talks.",
        }

    def build_inbound_greeting(self, elder_name: str) -> str:
        """Generate a greeting when the elder calls Cura."""
        return (
            f"Hello, {elder_name}. It's Cura. I'm glad you called. "
            f"What's on your mind? You can tell me anything, or just chat."
        )

    def build_inbound_menu(self) -> str:
        """Spoken menu for inbound calls."""
        return (
            "Press 1 if you'd like to chat. "
            "Press 2 if you have a question about your medications. "
            "Press 3 if you want to report something suspicious. "
            "Press 4 if you need help. "
            "Or just start talking — I'm listening."
        )

    def handle_inbound_choice(self, digit: str, elder_name: str) -> dict[str, str]:
        """Handle menu selection on an inbound call."""
        if digit == "1":
            return {
                "action": "chat",
                "say": f"I'd love to chat, {elder_name}. Tell me about your day. "
                       "How are you feeling?",
            }
        elif digit == "2":
            return {
                "action": "medication_question",
                "say": "Of course. What would you like to know about your medications? "
                       "I can remind you what you take and when.",
            }
        elif digit == "3":
            return {
                "action": "scam_report",
                "say": "I'm listening. Tell me what happened — who contacted you "
                       "and what did they ask for?",
            }
        elif digit == "4":
            # Through the guard, like every other help path. This one called the
            # callback directly and promised regardless (Vera, 2026-09-24).
            return {
                "action": "help_requested",
                "say": self._promise_help(
                    f"{elder_name} called and pressed 4 — needs help",
                    when_reachable="I'm contacting your family right now. "
                                   "Stay on the line with me. You're not alone."),
            }
        return {
            "action": "unknown",
            "say": "I didn't catch that. Just tell me what's on your mind, "
                   "or press 4 if you need help right away.",
        }

    @property
    def response_log(self) -> list[dict[str, Any]]:
        return list(self._response_log)
