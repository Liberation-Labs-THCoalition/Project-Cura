"""FS-ac721ea8069b — an_hour()'s range check can never fire.

    if not 1 <= h <= 12 and not 0 <= h <= 23:

Every h the regex can produce that is <= 23 satisfies the second clause, so the
`and` is false and nothing is rejected. "13pm" is accepted, to_hour24 adds 12,
and the wizard writes evening_time: 25. Setup prints "All set. Cura is ready."
`cura run` then dies before scheduling anything and the phone never rings.

RED = a value the wizard accepts becomes an hour no scheduler will take.
"""
import sys, pathlib
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from cura.setup.wizard import an_hour, to_hour24

ACCEPTED_BUT_IMPOSSIBLE = ["13pm", "15pm", "19pm", "23pm"]


@pytest.mark.parametrize("typed", ACCEPTED_BUT_IMPOSSIBLE)
def test_accepted_time_is_a_real_hour(typed):
    if an_hour(typed) is not None:
        return                      # rejected at the prompt: fine
    h = to_hour24(typed)
    assert 0 <= h <= 23, (
        f"the wizard accepted {typed!r} and wrote hour {h}. "
        "APScheduler refuses any hour above 23, so `cura run` exits before "
        "scheduling either check-in."
    )


def test_out_of_range_hour_is_rejected_at_the_prompt():
    assert an_hour("13pm") is not None, (
        "an_hour() accepts 13pm; the `not A and not B` guard is unreachable"
    )
