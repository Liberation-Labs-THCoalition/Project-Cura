"""Setup must not claim more than it has checked.

Every defect here came from the same shape: a promise printed unconditionally,
or a guard that accepted anything non-empty. "Cura is ready" is a claim about
the config, so it has to be checked against the config.
"""
from __future__ import annotations

import json

import pytest

from cura.comms.escalation import escalation_readiness
from cura.pulse.eldercare_pulse import ElderProfile
from cura.setup.wizard import (an_hour, norm_phone, readiness_problems,
                               to_hour24, write_config)


class TestHourValidation:
    @pytest.mark.parametrize("bad", ["13pm", "19pm", "25", "24", "99", "", "abc"])
    def test_impossible_hours_are_rejected(self, bad):
        """`not 1<=h<=12 and not 0<=h<=23` reduces to `not 0<=h<=23`, so 13-23
        passed a check whose message said "between 1 and 12". "13pm" became
        hour 25 and `cura run` died with an unhandled ValueError — the phone
        never rang, and setup had said "All set"."""
        assert an_hour(bad) is not None

    @pytest.mark.parametrize("good", ["8am", "7pm", "12am", "12pm", "0", "23"])
    def test_real_hours_are_accepted(self, good):
        assert an_hour(good) is None
        assert 0 <= to_hour24(good) <= 23

    def test_no_input_can_produce_an_impossible_hour(self):
        for v in ["13pm", "19pm", "23pm", "25", "99"]:
            if an_hour(v) is None:
                assert 0 <= to_hour24(v) <= 23, f"{v} produced an unusable hour"

    def test_an_empty_field_cannot_brick_setup(self):
        """m.group(1) on a failed match raised AttributeError inside finish(),
        so clearing a pre-filled time field bricked setup with a stack trace."""
        assert to_hour24("", default=8) == 8
        with pytest.raises(ValueError):
            to_hour24("")


class TestPhoneNormalisation:
    def test_empty_does_not_become_a_plus(self):
        """norm_phone("") returned "+", which is truthy and non-empty after
        strip — so a skipped question became an emergency contact Cura believed
        it could reach."""
        assert norm_phone("") == ""
        assert norm_phone("   ") == ""

    @pytest.mark.parametrize("bad", ["", "+", "555", "555-0134", "0123456789",
                                     "23075550134", "1234567890123"])
    def test_undialable_numbers_are_refused(self, bad):
        assert norm_phone(bad) == ""

    @pytest.mark.parametrize("good", ["307-555-0134", "13075550134",
                                      "(307) 555-0134", "+1 307 555 0134"])
    def test_real_numbers_normalise_to_e164(self, good):
        assert norm_phone(good) == "+13075550134"

    def test_both_wizards_share_one_rule(self):
        """Divergent validators on one shared state file is the two-halves
        defect in a different costume: wizard.ask() returns a stored answer
        without re-validating, so the window's answer reached the config under
        the terminal's rules."""
        from cura.setup.gui import _phone_ok
        for v in ["307-555-0134", "0123456789", "", "+", "23075550134"]:
            assert (_phone_ok(v) is None) == bool(norm_phone(v)), v


class TestEscalationGuardChecksDialability:
    def _profile(self, phone, contact):
        return ElderProfile(name="M", preferred_name="M", phone=phone,
                            emergency_contacts=[{"name": "Ray", "phone": contact}],
                            primary_caregiver={"name": "Ray", "phone": contact})

    def test_a_bare_plus_is_not_a_phone_number(self):
        assert escalation_readiness(self._profile("+13075550134", "+"))

    def test_an_invalid_area_code_is_not_reachable(self):
        assert escalation_readiness(self._profile("+13075550134", "+10123456789"))

    def test_a_real_number_passes(self):
        assert escalation_readiness(
            self._profile("+13075550134", "+13075550199")) == []


class TestSetupDoesNotDestroyCredentials:
    def test_rewriting_the_config_keeps_the_twilio_block(self, tmp_path):
        """add_phone writes twilio into this file; both wizards rebuilt cfg
        from scratch and wrote over it, so re-running setup silently deleted
        the credentials while still printing "All set. Cura is ready."
        install.sh re-runs setup, so this was reachable by following our own
        instructions."""
        out = tmp_path / "margaret.json"
        out.write_text(json.dumps({
            "name": "Margaret", "twilio": {"account_sid": "AC1",
                                           "auth_token": "secret"}}))
        write_config(out, {"name": "Margaret", "phone": "+13075550134"})
        after = json.loads(out.read_text())
        assert after["twilio"]["auth_token"] == "secret"
        assert after["phone"] == "+13075550134"

    def test_the_written_config_is_private(self, tmp_path):
        out = tmp_path / "m.json"
        write_config(out, {"name": "M"})
        assert oct(out.stat().st_mode & 0o777) == "0o600"


class TestReadyIsAClaimThatGetsChecked:
    BASE = {"name": "Margaret Chen", "preferred_name": "Margaret",
            "phone": "+13075550134"}

    def test_no_caregiver_means_not_ready(self):
        problems = readiness_problems(
            {**self.BASE, "emergency_contacts": [], "primary_caregiver": {}})
        assert problems and "nobody can be reached" in problems[0]

    def test_a_skipped_caregiver_phone_means_not_ready(self):
        assert readiness_problems({
            **self.BASE,
            "emergency_contacts": [{"name": "", "phone": "+"}],
            "primary_caregiver": {"name": "", "phone": "+"}})

    def test_a_complete_config_is_ready(self):
        assert readiness_problems({
            **self.BASE,
            "emergency_contacts": [{"name": "Ray", "phone": "+13075550199"}],
            "primary_caregiver": {"name": "Ray", "phone": "+13075550199"}}) == []

    def test_the_wizard_gates_its_ready_message(self):
        """The string must not be reachable without the check above it."""
        import inspect
        from cura.setup import wizard
        src = inspect.getsource(wizard.run)
        i = src.index("All set. Cura is ready.")
        assert "readiness_problems" in src[:i], \
            "'Cura is ready' is printed without checking readiness first"


class TestEveryCommandWePrintIsReal:
    """The wizards close by telling the household to type `cura rehearse` or
    `cura add-phone`. There was no `cura` command: install.sh built a venv and
    exec'd `python -m cura setup`, leaving nothing on PATH. Following our own
    closing instructions produced "command not found" — to a man who had
    already given up partway through one setup."""

    def test_the_package_declares_a_cura_entry_point(self):
        import tomllib
        from pathlib import Path
        repo = Path(__file__).resolve().parent.parent
        pyproject = repo / "pyproject.toml"
        assert pyproject.exists(), "no packaging file: `cura` cannot exist"
        data = tomllib.loads(pyproject.read_text())
        scripts = data.get("project", {}).get("scripts", {})
        assert "cura" in scripts, "no `cura` console script declared"
        assert scripts["cura"].startswith("cura.__main__:")

    def test_every_command_named_in_our_own_messages_is_a_real_subcommand(self):
        import argparse
        import re
        from pathlib import Path
        from cura.__main__ import main  # noqa: F401

        repo = Path(__file__).resolve().parent.parent
        promised = set()
        for py in (repo / "cura").rglob("*.py"):
            for m in re.finditer(r"cura (setup|rehearse|add-phone|run|console|webhook)\b",
                                 py.read_text()):
                promised.add(m.group(1))
        assert promised, "no commands found to check"

        src = (repo / "cura/__main__.py").read_text()
        real = set(re.findall(r"add_parser\(\s*[\"']([a-z-]+)[\"']", src))
        assert real, "could not read the real subcommand list"
        missing = promised - real
        assert not missing, f"we tell people to type commands that do not exist: {missing}"
