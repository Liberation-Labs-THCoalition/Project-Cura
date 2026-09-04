"""Telling her the help button exists.

Cura's <Gather>, its action URL, the escalation callback and the six-rung
ladder were built over four days, and NONE of it could ever fire, because no
scheduled call mentioned that a keypad existed. Verified against both
composers before this: neither said "press" anywhere.
"""
from __future__ import annotations

import pytest

from cura.pulse.checkin_composer import CheckinComposer
from cura.pulse.eldercare_pulse import ElderProfile, EldercarePulseConfig
from cura.pulse.help_prompt import (EARNEST_UNTIL, FAMILIAR_UNTIL,
                                    help_prompt, mentions_the_digit)


def _cfg():
    return EldercarePulseConfig(profile=ElderProfile(
        name="Margaret Chen", preferred_name="Margaret",
        medications=[{"name": "Warfarin", "time": "at bedtime"}]))


class TestEveryVariantStillSaysTheDigit:
    """The failure mode of a graduating script is a variant that gets funnier
    and stops being useful. The humour wraps the content; it never replaces it."""

    def test_every_variant_in_every_register_says_the_number(self):
        """One test over the whole space, not a 240-case cross product.

        The first version parametrised 40 days x 6 rotations, which asserted a
        single property 240 times and inflated the suite count by 257 without
        covering anything the loop below misses. A test count padded by a cross
        product reads as coverage and is not.
        """
        checked = 0
        for days in range(0, 40):
            for rotation in range(6):
                p = help_prompt(days, rotation=rotation)
                assert p is not None
                assert mentions_the_digit(p.text), \
                    f"day {days} rotation {rotation} drops the digit: {p.text!r}"
                checked += 1
        assert checked == 240

    def test_even_the_offer_to_skip_it_still_says_it(self):
        texts = [help_prompt(30, rotation=r).text for r in range(6)]
        skipper = [t for t in texts if "skip" in t.lower()]
        assert skipper, "the skip variant is missing"
        assert all(mentions_the_digit(t) for t in skipper)


class TestItGraduates:
    def test_earnest_first(self):
        assert help_prompt(0).stage == "earnest"
        assert help_prompt(EARNEST_UNTIL - 1).stage == "earnest"

    def test_then_familiar(self):
        assert help_prompt(EARNEST_UNTIL).stage == "familiar"
        assert help_prompt(FAMILIAR_UNTIL - 1).stage == "familiar"

    def test_then_playful(self):
        assert help_prompt(FAMILIAR_UNTIL).stage == "playful"
        assert help_prompt(365).stage == "playful"

    def test_no_joke_in_the_first_fortnight(self):
        """The joke only reads as warmth once the information is old news."""
        for d in range(FAMILIAR_UNTIL):
            for r in range(6):
                assert help_prompt(d, rotation=r).stage != "playful"

    def test_rotation_varies_the_wording_within_a_register(self):
        seen = {help_prompt(30, rotation=r).text for r in range(6)}
        assert len(seen) > 1, "playful register never varies"

    def test_rotation_is_deterministic_so_rehearse_shows_the_truth(self):
        assert help_prompt(20, rotation=3).text == help_prompt(20, rotation=3).text


class TestNeverOnInbound:
    def test_someone_who_dialled_cura_gets_no_menu(self):
        """They have already proved they can reach it. Reading them a menu is
        the IVR behaviour this replaces."""
        assert help_prompt(0, inbound=True) is None
        assert help_prompt(365, inbound=True) is None


class TestTheComposersActuallySayIt:
    """The wiring, not the wording. This is the half that was missing."""

    @pytest.mark.parametrize("which,day", [
        ("compose_morning", 0), ("compose_morning", 20),
        ("compose_evening", 0), ("compose_evening", 20),
    ])
    def test_every_scheduled_call_mentions_a_key(self, which, day):
        msgs = getattr(CheckinComposer(), which)(
            _cfg(), days_heard=day, rotation=day).all_messages
        joined = " ".join(msgs).lower()
        assert "press two" in joined or " two" in joined, \
            f"{which} on day {day} never tells her a key exists"

    @pytest.mark.parametrize("which", ["compose_morning", "compose_evening"])
    def test_it_is_the_last_thing_she_hears(self, which):
        """Last, so it is most recent when the <Gather> opens."""
        msgs = getattr(CheckinComposer(), which)(
            _cfg(), days_heard=0, rotation=0).all_messages
        assert mentions_the_digit(msgs[-1])

    def test_the_greeting_is_still_first(self):
        msgs = CheckinComposer().compose_morning(
            _cfg(), days_heard=0, rotation=0).all_messages
        assert "Margaret" in msgs[0]
