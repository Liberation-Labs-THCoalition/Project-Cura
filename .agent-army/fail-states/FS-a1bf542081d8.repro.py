"""FS-a1bf542081d8 — the keypad means opposite things and is never explained.

`cura run` speaks the composer's check-in and places the call with
gather_response=True, so a digit is collected. CuraResponder.handle_dtmf then
assigns that digit a meaning that depends on the time of day:

    morning ("checkin"):  1 -> medication_confirmed   2 -> help_requested
    evening ("evening"):  1 -> help_requested         2 -> all_good

Nothing spoken on either call tells him which key does what. The composer never
utters the word "press"; the only scripts that do (CuraVoice.morning_checkin /
evening_checkin) are not on the path `cura run` takes. So the last thing he
actually hears before the beep is whichever enrichment came last — "Have you had
breakfast?" in the morning, "Do you have grab bars in your bathroom?" in the
evening — and the answer to that question is recorded as a medication
confirmation, or as a call for help, or as "all good, sleep well".

Answering "yes, I had breakfast" is filed as "she took her pills" and reaches the
caregiver as "Meds: all confirmed". Answering "no" at night is filed as all_good
and the evening's request for help is discarded.

No test in the suite pairs what is spoken with what the digit is taken to mean.
"""
from __future__ import annotations

from cura.comms.responder import CuraResponder
from cura.comms.voice import CuraVoice
from cura.pulse.checkin_composer import CheckinComposer
from cura.pulse.eldercare_pulse import ElderProfile, EldercarePulseConfig


def _household():
    """The shape `cura run` builds from a wizard-written config."""
    return EldercarePulseConfig(ElderProfile(
        name="Robert Edrington", preferred_name="Bob",
        phone="+13075550143",
        medications=[{"name": "Donepezil", "time": "morning"},
                     {"name": "Amlodipine", "time": "evening"}],
        primary_caregiver={"name": "Sarah", "phone": "+13075550188"},
        morning_time=9, evening_time=18,
    ))


def test_the_checkin_says_which_key_to_press():
    composer = CheckinComposer()
    config = _household()
    for label, checkin in (("morning", composer.compose_morning(config)),
                           ("evening", composer.compose_evening(config))):
        spoken = " ".join(checkin.all_messages).lower()
        assert "press" in spoken, (
            f"the {label} check-in collects a keypad digit (gather_response=True "
            f"in cura/__main__.py) but never says what to press. Last thing he "
            f"hears: {checkin.all_messages[-1]!r}"
        )


def test_a_digit_does_not_mean_opposite_things_at_different_times_of_day():
    responder = CuraResponder()
    clashes = []
    for digit in ("1", "2"):
        morning = responder.handle_dtmf(digit, "checkin")["action"]
        evening = responder.handle_dtmf(digit, "evening")["action"]
        if morning != evening:
            clashes.append(f"{digit}: morning={morning} evening={evening}")
    assert not clashes, (
        "the same key is read as a different answer depending on the hour, and "
        "neither call explains it: " + "; ".join(clashes)
    )


def test_the_gather_routes_the_digit_to_the_response_endpoint():
    twiml = CuraVoice(dry_run=True)._build_twiml(["Good morning, Bob."], gather=True)
    assert "<Gather" in twiml
    assert "action=" in twiml, (
        "the Gather element carries no action attribute, so the digit is not "
        "posted to /voice/checkin-response. status_callback is a call-lifecycle "
        "URL, not the Gather action: " + twiml
    )
