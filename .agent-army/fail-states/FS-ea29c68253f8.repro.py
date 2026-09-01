"""FS-ea29c68253f8 — the evening check-in says goodnight, then keeps talking.

compose_evening() uses generate_evening_summary() as the greeting. That summary
ends with "Is there anything you need before bed?" — a closing question — and
all_messages then appends memory touches, wearable notes, up to three
enrichments and a scam tip after it. The listener is asked whether she needs
anything before bed and then spoken at four more times.

The same change that landed the "stops sounding like a person" rule on
all_messages also moved the evening medication line inside that summary, so the
closer is now buried further from the end.

RED = the closing question is not the last thing said.
"""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from cura.pulse.eldercare_pulse import ElderProfile, EldercarePulseConfig
from cura.pulse.checkin_composer import CheckinComposer

CLOSER = "Is there anything you need before bed?"


def _evening():
    p = ElderProfile(name="Robert Ellsworth", preferred_name="Robert",
                     phone="+13075550142",
                     medications=[{"name": "Amlodipine", "time": "evening"}],
                     emergency_contacts=[], primary_caregiver={}, address="",
                     morning_time=8, evening_time=19)
    return CheckinComposer().compose_evening(EldercarePulseConfig(p)).all_messages


def test_nothing_is_said_after_goodnight():
    msgs = _evening()
    said_closer = [i for i, m in enumerate(msgs) if CLOSER in m]
    assert said_closer, "the evening check-in no longer closes; update this case"
    after = msgs[said_closer[0] + 1:]
    assert not after, (
        "Cura asks %r and then says %d more things: %s"
        % (CLOSER, len(after), " / ".join(after))
    )
