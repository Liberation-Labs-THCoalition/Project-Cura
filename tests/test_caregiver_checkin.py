"""The call that asks after the caregiver.

CaregiverBurnoutCheck has existed for weeks — four written messages, a docstring
saying "nobody checks on the checkers", and tests. It is IMPORTED by
checkin_composer.py and never instantiated. The words for "Cura asks after the
father" were written, tested, imported, and never spoken aloud.

It could not be wired before: Cura had one profile, every call went to the
person being cared for, and the caregiver's number existed only to receive
alerts. He was structurally an alarm recipient.
"""
from __future__ import annotations

import pytest

from cura.household import Household, Member, Reach
from cura.pulse.caregiver_checkin import compose_caregiver_checkin
from cura.pulse.daily_enrichments import CaregiverBurnoutCheck
from cura.pulse.medication import needs_clarification

MEDS = [{"name": "Oxycodone", "time": "as needed for pain"},
        {"name": "Donepezil", "time": ""},
        {"name": "Alendronate", "time": "on Sundays"}]


def _house():
    return Household({
        "margaret": Member("margaret", "Margaret Chen", "Margaret",
                           "+13075550134", Reach.NEVER, medications=MEDS),
        "ray": Member("ray", "Ray Chen", "Ray", "+13075550199",
                      Reach.SCHEDULED, cares_for=("margaret",)),
    })


class TestItAsksAfterHimFirst:
    def test_the_first_line_is_about_him_not_her(self):
        """Not a status report with a wellbeing question bolted on."""
        first = compose_caregiver_checkin(_house(), "ray", rotation=0).lines[0]
        assert "Ray" in first
        assert any(w in first.lower() for w in
                   ("how are you", "you matter", "check in on you"))

    def test_a_household_with_no_questions_is_just_the_check_in(self):
        c = compose_caregiver_checkin(_house(), "ray", rotation=1)
        assert len(c.lines) == 2      # the question, and the support offer


class TestItSaysTheRealReasonPerMedication:
    """"I don't know when this is taken" is a gap. "This is as-needed and I
    wasn't told the interval" means Cura is GUARDING the drug and cannot answer
    "may I take another". Collapsing them into "I'm not reminding her about
    these" tells him something false about the first and nothing about the
    second."""

    def _lines(self):
        return compose_caregiver_checkin(
            _house(), "ray", rotation=0,
            medication_questions=needs_clarification(MEDS)).lines

    def test_each_medication_gets_its_own_reason(self):
        joined = " ".join(self._lines())
        assert "how long to wait" in joined          # the PRN one
        assert "don't know when this one is taken" in joined
        assert "not what time of day" in joined      # the weekly one

    def test_the_prn_drug_is_not_described_as_unreminded(self):
        prn = [l for l in self._lines() if "Oxycodone" in l]
        assert prn and "not reminding" not in prn[0].lower()


class TestHeIsToldWhatCuraIsNotHandling:
    def test_open_gaps_are_spoken(self):
        h = _house()
        c = compose_caregiver_checkin(h, "ray", rotation=0,
                                      open_gaps=h.reportable_gaps())
        joined = " ".join(c.lines)
        assert "nobody else for Cura to call" in joined, \
            "he is not told he is the single point of failure"


class TestRotationNotRandomness:
    def test_the_same_rotation_gives_the_same_words(self):
        a = compose_caregiver_checkin(_house(), "ray", rotation=2).lines[0]
        b = compose_caregiver_checkin(_house(), "ray", rotation=2).lines[0]
        assert a == b, "cura rehearse cannot show what he will actually hear"

    def test_rotation_varies_the_opening(self):
        seen = {compose_caregiver_checkin(_house(), "ray", rotation=r).lines[0]
                for r in range(4)}
        assert len(seen) == 4


class TestTheUnverifiedHelplineIsNotSpoken:
    """Speaking a wrong number to an exhausted caregiver at 2am costs them the
    one call they worked up to making. The number in RESOURCES was written into
    the source and never dialled."""

    def test_the_number_is_gated_until_verified(self):
        b = CaregiverBurnoutCheck()
        assert b.resource_is_verified is False
        assert "855" not in b.spoken_resource()

    def test_the_support_offer_still_happens(self):
        assert "not have to do this alone" in \
            CaregiverBurnoutCheck().spoken_resource().replace("don't", "do not")

    def test_no_unverified_number_reaches_the_call(self):
        joined = " ".join(compose_caregiver_checkin(_house(), "ray").lines)
        assert "855" not in joined and "1-8" not in joined
