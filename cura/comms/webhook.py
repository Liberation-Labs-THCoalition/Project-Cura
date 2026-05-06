"""Webhook server — Twilio calls this when Margaret responds.

A minimal Flask app that:
  1. Handles DTMF (keypad presses) during check-in calls
  2. Handles speech transcription during calls
  3. Handles inbound calls (Margaret calls Cura)
  4. Returns TwiML telling Twilio what to say next

Run standalone for development:
  python -m cura.comms.webhook --port 5000

In production, put this behind ngrok or a reverse proxy so
Twilio can reach it.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_responder = None
_elder_name = ""
_voice = "Polly.Joanna"
_rate = "slow"


def _say(text: str) -> str:
    """Build a TwiML Say element."""
    return f'<Say voice="{_voice}" rate="{_rate}">{text}</Say>'


def _gather(text: str, action_path: str, input_type: str = "dtmf speech") -> str:
    """Build a TwiML Gather element that speaks and waits for input."""
    return (
        f'<Gather input="{input_type}" timeout="10" action="{action_path}">'
        f'{_say(text)}'
        f'</Gather>'
        f'{_say("I didn\'t hear a response. I\'ll check back later. Take care.")}'
    )


def create_app(
    responder=None,
    elder_name: str = "",
    voice: str = "Polly.Joanna",
    rate: str = "slow",
):
    """Create the Flask webhook app.

    Args:
        responder: CuraResponder instance
        elder_name: Elder's preferred name
        voice: Twilio TTS voice
        rate: Twilio TTS rate
    """
    try:
        from flask import Flask, request
    except ImportError:
        logger.error("Flask not installed — pip install flask")
        raise

    global _responder, _elder_name, _voice, _rate
    _responder = responder
    _elder_name = elder_name
    _voice = voice
    _rate = rate

    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health():
        return "ok", 200

    @app.route("/voice/checkin-response", methods=["POST"])
    def checkin_response():
        """Handle response during a scheduled check-in call."""
        digits = request.form.get("Digits", "")
        speech = request.form.get("SpeechResult", "")

        if _responder is None:
            return _twiml(_say("Thank you. Goodbye.")), 200

        if digits:
            result = _responder.handle_dtmf(digits, "checkin")
        elif speech:
            result = _responder.handle_speech(speech, "checkin")
        else:
            result = {"say": "I didn't catch that. Goodbye for now."}

        return _twiml(_say(result["say"])), 200

    @app.route("/voice/evening-response", methods=["POST"])
    def evening_response():
        """Handle response during evening check-in."""
        digits = request.form.get("Digits", "")
        speech = request.form.get("SpeechResult", "")

        if _responder is None:
            return _twiml(_say("Sleep well. Goodbye.")), 200

        if digits:
            result = _responder.handle_dtmf(digits, "evening")
        elif speech:
            result = _responder.handle_speech(speech, "evening")
        else:
            result = {"say": "Sleep well tonight. I'll talk to you in the morning."}

        return _twiml(_say(result["say"])), 200

    @app.route("/voice/inbound", methods=["POST"])
    def inbound_call():
        """Handle an inbound call — Margaret called Cura."""
        if _responder is None:
            return _twiml(_say("Hello. Cura is not available right now. Goodbye.")), 200

        greeting = _responder.build_inbound_greeting(_elder_name)
        menu = _responder.build_inbound_menu()
        body = _gather(
            f"{greeting} {menu}",
            "/voice/inbound-response",
        )
        return _twiml(body), 200

    @app.route("/voice/inbound-response", methods=["POST"])
    def inbound_response():
        """Handle menu selection or speech on inbound call."""
        digits = request.form.get("Digits", "")
        speech = request.form.get("SpeechResult", "")

        if _responder is None:
            return _twiml(_say("Thank you for calling. Goodbye.")), 200

        if digits:
            result = _responder.handle_inbound_choice(digits, _elder_name)
        elif speech:
            result = _responder.handle_speech(speech, "inbound")
        else:
            result = {"say": "I'm here whenever you need me. Call back anytime."}

        if result.get("action") in ("chat", "scam_report", "medication_question"):
            body = _gather(result["say"], "/voice/inbound-chat")
            return _twiml(body), 200

        return _twiml(_say(result["say"])), 200

    @app.route("/voice/inbound-chat", methods=["POST"])
    def inbound_chat():
        """Ongoing conversation turn during inbound call."""
        speech = request.form.get("SpeechResult", "")

        if _responder and speech:
            result = _responder.handle_speech(speech, "inbound")
            body = _gather(
                result["say"] + " Is there anything else?",
                "/voice/inbound-chat",
            )
            return _twiml(body), 200

        return _twiml(_say(
            "It was lovely talking to you. Call me anytime. Take care."
        )), 200

    @app.route("/voice/status", methods=["POST"])
    def call_status():
        """Twilio call status callback — logging only."""
        status = request.form.get("CallStatus", "")
        duration = request.form.get("CallDuration", "0")
        logger.info("Call status: %s, duration: %ss", status, duration)
        return "", 204

    return app


def _twiml(body: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'


if __name__ == "__main__":
    import argparse
    from cura.comms.responder import CuraResponder

    parser = argparse.ArgumentParser(description="Cura webhook server")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--elder-name", type=str, default="friend")
    args = parser.parse_args()

    responder = CuraResponder()
    app = create_app(responder=responder, elder_name=args.elder_name)
    app.run(host="0.0.0.0", port=args.port, debug=True)
