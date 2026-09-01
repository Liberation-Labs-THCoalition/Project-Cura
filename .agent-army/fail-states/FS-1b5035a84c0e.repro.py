"""FS-1b5035a84c0e — the inbound endpoint greets whoever dials, by name.

/voice/inbound never reads request.form["From"]. Every caller gets

    "Hello, Margaret. It's Cura. I'm glad you called. What's on your mind?
     You can tell me anything, or just chat. ... Press 3 if you want to report
     something suspicious. Press 4 if you need help."

There is no check that the caller is the resident, or the caregiver, or anyone
at all. Cura's number is a purchased Twilio number: it inherits whatever call
history the previous owner left, it gets wrong numbers, and it gets the same
autodialers every US number gets.

What reaches the household, in order of how much it costs her:

  1. The greeting hands the resident's first name to any caller. Cura's whole
     defensive premise (cura/privacy/scam_shield.py) is that a stranger who
     already knows her name is the opening move of an elder-fraud call. This
     endpoint gives that away to anyone who dials.
  2. Press 4 fires on_help_requested and pages the caregiver. A wrong number
     that mashes the keypad wakes an exhausted 70-year-old at 3am.
  3. "Press 3 ... tell me what happened" opens a speech channel that
     handle_speech() treats as the resident talking.

The fix is not a wall: it is checking From against the resident's and the
caregiver's numbers and giving an unrecognised caller a neutral greeting with
no name in it.

RED = an inbound POST from an unknown number is answered with the elder's name.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

SOURCE = (pathlib.Path(__file__).resolve().parents[2]
          / "cura" / "comms" / "webhook.py").read_text()


def test_inbound_route_looks_at_the_calling_number():
    """Static half: runs everywhere, including where Flask is absent."""
    assert '"From"' in SOURCE or "'From'" in SOURCE or "Caller" in SOURCE, (
        "cura/comms/webhook.py never reads the From field on an inbound call. "
        "Every caller is treated as the resident and greeted by her name."
    )


def test_unknown_caller_is_not_greeted_by_name():
    """Live half: only runs where Flask is installed."""
    try:
        import flask  # noqa: F401
    except ImportError:
        return
    from cura.comms.responder import CuraResponder
    from cura.comms.webhook import create_app

    paged = []
    responder = CuraResponder(on_help_requested=lambda m: paged.append(m))
    client = create_app(responder=responder, elder_name="Margaret").test_client()

    body = client.post(
        "/voice/inbound",
        data={"From": "+15550009999", "CallSid": "CAdeadbeef"},
    ).get_data(as_text=True)
    assert "Margaret" not in body, (
        "an inbound call from an unrecognised number was answered "
        f"'Hello, Margaret'. Body: {body[:200]}"
    )

    client.post("/voice/inbound-response",
                data={"From": "+15550009999", "Digits": "4"})
    assert not paged, (
        "an unrecognised caller pressed 4 and paged the caregiver: "
        f"{paged}"
    )
