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


def _install_twilio_signature_check(app, auth_token: str, public_url: str = ""):
    """Reject any request that Twilio did not sign.

    Without this every route is open to anyone who learns the URL. Verified by
    audit: an unsigned POST of Digits=1 to /voice/checkin-response returned 200
    and fired on_medication_confirmed. That means a stranger -- or a scanner --
    could tell Cura the medication was taken, and Cura would believe it and stop
    following up. For a household where the whole point is noticing when she
    did not take it, a forged confirmation is the most damaging thing you can
    inject, and it looks exactly like success.

    Twilio signs each request over the exact URL it called plus the sorted POST
    body. The URL must match what Twilio used, which is why the public URL is
    configurable rather than taken from the Host header -- a proxy that rewrites
    Host silently breaks every signature and the failure looks like an attack.

    Refuses to install without a token rather than allowing everything: an
    auth layer that silently no-ops is worse than none, because it reports as
    present.
    """
    from flask import request, abort

    if not auth_token:
        raise RuntimeError(
            "Cura will not serve webhooks without a Twilio auth token to verify "
            "signatures with. Anyone who found the URL could confirm medications "
            "on the resident's behalf.")

    try:
        from twilio.request_validator import RequestValidator
    except ImportError:
        raise RuntimeError(
            "twilio package is required to verify webhook signatures; refusing "
            "to serve unverified requests.")

    validator = RequestValidator(auth_token)

    @app.before_request
    def _verify():
        if request.path == "/health" and request.method == "GET":
            return None
        base = (public_url or "").rstrip("/")
        url = base + request.full_path.rstrip("?") if base else request.url
        signature = request.headers.get("X-Twilio-Signature", "")
        if not validator.validate(url, request.form.to_dict(), signature):
            logger.error(
                "REJECTED UNSIGNED OR MISSIGNED REQUEST to %s from %s",
                request.path, request.remote_addr)
            abort(403)
        return None


def create_app(
    responder=None,
    elder_name: str = "",
    voice: str = "Polly.Joanna",
    rate: str = "slow",
    auth_token: str = "",
    public_url: str = "",
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
    _install_twilio_signature_check(app, auth_token=auth_token,
                                    public_url=public_url)

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

    # Standalone entrypoint. It cannot build an escalation path (it has no
    # config), so it refuses rather than serving a Cura that promises help it
    # cannot send. Use "cura webhook --config ..." instead.
    print("Run this through the CLI so Cura knows who to call for help:")
    print("    cura webhook --config <the file setup created>")
    raise SystemExit(1)
