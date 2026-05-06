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
                if self._on_help:
                    self._on_help("Elder pressed 2 — needs help")
                return {
                    "action": "help_requested",
                    "say": "I'm letting your family know right now. "
                           "Stay where you are and someone will check on you soon. "
                           "You're not alone.",
                }
            elif digit == "9":
                return {
                    "action": "repeat",
                    "say": "Of course, let me repeat that.",
                }

        if call_context == "evening":
            if digit == "1":
                if self._on_help:
                    self._on_help("Elder needs something before bed")
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
            if self._on_help:
                self._on_help(f"Elder said: {transcript[:200]}")
            return {
                "action": "help_requested",
                "say": "I'm alerting your family right now. Stay calm, stay safe. "
                       "Help is on the way.",
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
            if self._on_help:
                self._on_help(f"{elder_name} called and pressed 4 — needs help")
            return {
                "action": "help_requested",
                "say": "I'm contacting your family right now. Stay on the line with me. "
                       "You're not alone.",
            }
        return {
            "action": "unknown",
            "say": "I didn't catch that. Just tell me what's on your mind, "
                   "or press 4 if you need help right away.",
        }

    @property
    def response_log(self) -> list[dict[str, Any]]:
        return list(self._response_log)
