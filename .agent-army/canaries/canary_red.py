"""CANARY-red fixture.

This test asserts its own failure, every run, forever. Its only job is to
prove the replay runner can still see a failing case. If replay.py ever
reports anything other than FAIL for CANARY-red, the runner has stopped
detecting failure and every other verdict it prints is worthless.

This is a self-referential assertion, not a planted vulnerability. A real
planted flaw would be re-discovered by the audit agents and would trip
security scanners; this cannot be mistaken for a defect in the product.
"""


def test_canary_red_always_fails():
    assert False, (
        "CANARY-red: this assertion is supposed to fail. "
        "If you are reading this in a passing run, the harness is lying."
    )
