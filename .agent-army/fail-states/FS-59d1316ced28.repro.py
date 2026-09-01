r"""FS-59d1316ced28 — medication_slots reads a dose quantity as a clock time.

_CLOCK is `\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b` and is applied with .search(),
so it matches the FIRST one- or two-digit number anywhere in the `time` field.
"1 tab at 7pm" yields hour=1, not 19, and the medication is announced at the
morning check-in and never at the evening one.

RED = a medication recorded for the evening is placed in the morning slot.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pytest
from cura.pulse.eldercare_pulse import medication_slots

# (recorded time, the check-in it must be spoken in, the one it must NOT be in)
CASES = [
    ("1 tab at 7pm",       "evening", "morning"),
    ("2 pills, 9pm",       "evening", "morning"),
    ("take 2 tablets at 8pm", "evening", "morning"),
    ("0.5 tablet at 9pm",  "evening", "morning"),
]


@pytest.mark.parametrize("recorded,due,forbidden", CASES)
def test_dose_quantity_is_not_a_clock_time(recorded, due, forbidden):
    slots = medication_slots({"name": "Donepezil", "time": recorded})
    assert forbidden not in slots, (
        f"{recorded!r} put Donepezil in the {forbidden} check-in. "
        "Someone who cannot recall whether she already took it is being "
        "prompted at the wrong end of the day."
    )
    assert due in slots, f"{recorded!r} never reaches the {due} check-in"


def test_twice_daily_frequency_is_not_one_slot():
    # "every 12 hours" is a q12h regimen, not a 12 o'clock dose.
    slots = medication_slots({"name": "Metformin", "time": "every 12 hours"})
    assert slots == {"morning", "evening"}, (
        f"q12h resolved to {slots or 'nothing'}; one of the two daily doses "
        "is never prompted and nothing flags it."
    )


def test_three_times_a_day_is_not_three_oclock():
    slots = medication_slots({"name": "Sinemet", "time": "3 times a day"})
    assert slots == {"morning", "evening"}, (
        f"'3 times a day' resolved to {slots or 'nothing'} — the count was "
        "read as an hour."
    )
