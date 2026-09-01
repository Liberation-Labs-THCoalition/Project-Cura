"""FS-77fd64629ccf — the webhook authenticates nothing.

create_app() registers five POST routes and validates no request. Twilio signs
every webhook it sends with X-Twilio-Signature; Cura never looks at the header,
never constructs a twilio.request_validator.RequestValidator, and never checks
the auth token against the request. The module docstring says to put this behind
ngrok -- a public URL with no auth in front of it.

What reaches the household:

  POST /voice/checkin-response  Digits=1
      -> responder.handle_dtmf("1", "checkin") -> on_medication_confirmed()

  Anyone on the internet can mark the morning dose as taken. The one signal that
  a dose was MISSED is the absence of that confirmation, and a stranger -- or a
  scanner walking the ngrok URL space -- can supply it. A missed dose then reads
  as a taken dose and no one is told. That is the silent failure this project
  says is the dangerous one.

  POST /voice/checkin-response  Digits=2  -> on_help_requested()
      Forged distress in the other direction: alerts the caregiver at 3am to a
      fall that did not happen. A caregiver who stops believing the alerts is a
      caregiver who misses the real one.

RED = the endpoints accept an unsigned request and act on it.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

SOURCE = (pathlib.Path(__file__).resolve().parents[2]
          / "cura" / "comms" / "webhook.py").read_text()

VALIDATION_MARKERS = ("RequestValidator", "X-Twilio-Signature", "X_TWILIO_SIGNATURE",
                      "x-twilio-signature", "validate_twilio", "twilio_signature")


def test_webhook_module_validates_twilio_signatures():
    """Static half: runs everywhere, including where Flask is absent."""
    assert any(m in SOURCE for m in VALIDATION_MARKERS), (
        "cura/comms/webhook.py contains no Twilio signature validation. "
        "Every route is open to anyone who can reach the URL, and the module "
        "docstring tells the operator to expose it through ngrok."
    )


def test_forged_dtmf_cannot_confirm_a_medication():
    """Live half: only runs where Flask is installed; static half covers the rest."""
    try:
        import flask  # noqa: F401
    except ImportError:
        return
    from cura.comms.responder import CuraResponder
    from cura.comms.webhook import create_app

    fired = []
    responder = CuraResponder(
        on_medication_confirmed=lambda: fired.append("MEDS_CONFIRMED"),
        on_help_requested=lambda msg: fired.append("HELP:" + msg),
    )
    client = create_app(responder=responder, elder_name="Margaret").test_client()

    resp = client.post("/voice/checkin-response", data={"Digits": "1"})
    assert "MEDS_CONFIRMED" not in fired, (
        f"an unsigned POST recorded the morning dose as taken (HTTP {resp.status_code}). "
        "A dose that was actually missed now looks taken and nobody is told."
    )

    client.post("/voice/checkin-response", data={"Digits": "2"})
    assert not any(f.startswith("HELP:") for f in fired), (
        "an unsigned POST raised a help request; the caregiver escalation "
        "channel accepts input from anyone who can reach the URL."
    )


def test_a_bogus_signature_header_is_rejected():
    try:
        import flask  # noqa: F401
    except ImportError:
        return
    from cura.comms.responder import CuraResponder
    from cura.comms.webhook import create_app

    client = create_app(responder=CuraResponder(), elder_name="Margaret").test_client()
    resp = client.post("/voice/checkin-response", data={"Digits": "1"},
                       headers={"X-Twilio-Signature": "not-a-real-signature=="})
    assert resp.status_code in (401, 403), (
        f"a request carrying a garbage X-Twilio-Signature was answered "
        f"{resp.status_code}; the header is never read."
    )
