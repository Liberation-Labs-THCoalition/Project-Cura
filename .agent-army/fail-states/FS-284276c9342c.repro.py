"""FS-284276c9342c — the window's phone validator is a divergent duplicate.

gui.py._phone_ok accepts any 10 or 11 digits. wizard.py.a_phone accepts 10, or
11 only when the first is a 1. The two wizards share one state file, so the same
answer is legal in one and not the other, and the window turns "0307-555-0142"
into "+03075550142" — no country code begins with 0, so Twilio can never place
that call and the phone simply never rings.

This is the same duplication that caused FS-1 (a stricter copy of the hour
parser crashed the Finish button). That one was fixed by importing the wizard's
validator; these two were left copied.

RED = the two validators disagree, and the window writes an impossible number.
"""
import re, sys, pathlib
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from cura.setup.wizard import a_phone, norm_phone
from cura.setup.gui import _phone_ok, _norm_phone

TYPED = ["307-555-0142", "13075550142", "0307-555-0142",
         "555-123-45677", "3075550142 7"]


@pytest.mark.parametrize("typed", TYPED)
def test_both_wizards_agree(typed):
    assert (a_phone(typed) is None) == (_phone_ok(typed) is None), (
        f"{typed!r}: terminal wizard "
        f"{'accepts' if a_phone(typed) is None else 'rejects'} it, window "
        f"{'accepts' if _phone_ok(typed) is None else 'rejects'} it"
    )


@pytest.mark.parametrize("typed", TYPED)
def test_anything_accepted_is_dialable(typed):
    if _phone_ok(typed) is not None:
        return
    written = _norm_phone(typed)
    assert re.fullmatch(r"\+[1-9]\d{7,14}", written), (
        f"the window accepted {typed!r} and wrote {written!r}, which is not a "
        "number any carrier will dial"
    )
