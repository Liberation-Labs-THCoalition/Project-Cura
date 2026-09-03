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

    def test_every_flag_named_in_our_own_messages_is_a_real_flag(self):
        """The first version of this test checked subcommand names only, so it
        passed while a message told the household to run `cura setup --again`,
        a flag that did not exist. I introduced that string in the commit
        immediately after fixing this exact class of defect, and the test I had
        just written did not catch it."""
        import argparse
        import re
        from pathlib import Path
        from cura.__main__ import main  # noqa: F401

        repo = Path(__file__).resolve().parent.parent
        promised = set()
        for py in list((repo / "cura").rglob("*.py")) + [repo / "install.sh"]:
            if not py.exists():
                continue
            for m in re.finditer(r"cura ([a-z-]+)((?:\s+--[a-z-]+)+)", py.read_text()):
                for flag in re.findall(r"--[a-z-]+", m.group(2)):
                    promised.add((m.group(1), flag))
        src = (repo / "cura/__main__.py").read_text()
        for cmd, flag in sorted(promised):
            block = src.split(f'add_parser(\n        "{cmd}"')[-1] \
                if f'"{cmd}"' in src else src
            assert flag in src, \
                f"we tell people to run `cura {cmd} {flag}` and {flag} does not exist"

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


class TestTheTwoWizardsAgreeOnEverything:
    """Not just the validator. I unified _phone_ok and left _norm_phone
    divergent in the same file, so the window still turned a skipped question
    into the emergency contact "+". The window is the path the packaged
    double-clickable app launches — the one a man with failing eyesight gets."""

    @pytest.mark.parametrize("value", [
        "", "   ", "+", "555", "307-555-0134", "13075550134",
        "0123456789", "(307) 555-0134", "23075550134",
    ])
    def test_both_normalisers_return_the_same_thing(self, value):
        from cura.setup.gui import _norm_phone
        assert _norm_phone(value) == norm_phone(value)

    @pytest.mark.parametrize("value", ["", "   ", "+", "555"])
    def test_neither_turns_a_skipped_question_into_a_phone_number(self, value):
        from cura.setup.gui import _norm_phone
        assert _norm_phone(value) == ""
        assert norm_phone(value) == ""


class TestMultipleHouseholdMembersAreExplained:
    """_default_config_path returns None for zero configs AND for two, and both
    call sites printed "Cura isn't set up yet — run cura setup". For a household
    that set up two people that is simply false, and it sends someone who
    already did the work back to do it again. The household model makes two
    configs normal, so this had to stop lying first."""

    def _explain(self, tmp_path, monkeypatch, names, command="run"):
        import io, contextlib
        from pathlib import Path
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        d = tmp_path / ".cura"
        d.mkdir(parents=True, exist_ok=True)
        for n in names:
            (d / n).write_text("{}")
        from cura.__main__ import _explain_no_config
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _explain_no_config(command=command)
        return buf.getvalue()

    def test_no_config_says_run_setup(self, tmp_path, monkeypatch):
        out = self._explain(tmp_path, monkeypatch, [])
        assert "isn't set up yet" in out and "cura setup" in out

    def test_two_configs_names_both_instead_of_claiming_unconfigured(
            self, tmp_path, monkeypatch):
        out = self._explain(tmp_path, monkeypatch, ["margaret.json", "ray.json"])
        assert "isn't set up yet" not in out, "told a set-up household to set up"
        assert "margaret.json" in out and "ray.json" in out

    def test_it_names_the_command_the_person_actually_typed(
            self, tmp_path, monkeypatch):
        out = self._explain(tmp_path, monkeypatch,
                            ["margaret.json", "ray.json"], command="rehearse")
        assert "cura rehearse --config" in out
        assert "cura run --config" not in out

    def test_setup_progress_is_not_offered_as_a_person(
            self, tmp_path, monkeypatch):
        out = self._explain(tmp_path, monkeypatch,
                            ["margaret.json", "ray.json", "setup-progress.json"])
        assert "setup-progress" not in out


class TestAnUnreadableConfigIsNotAnEmptyOne:
    """`existing = {}` on a ValueError made the merge discard everything —
    including the Twilio auth token — which is the exact loss write_config
    exists to prevent, reachable through a file that is merely corrupt. Silent:
    no error, no backup, the credentials simply gone.

    Found by a question from Nexus, who asked whether the merge preserves
    comments before writing public_url into the config. It does not, because
    the format is strict JSON — but a commented config is unparseable, and
    unparseable was being read as empty. Their installer writes this file.
    """

    def _corrupt(self, tmp_path, text):
        p = tmp_path / "margaret.json"
        p.write_text(text)
        return p

    @pytest.mark.parametrize("text,label", [
        ('{ // a note\n "name": "M", "twilio": {"auth_token": "secret"}}', "comments"),
        ('{"name": "M", "twilio": {"auth_to', "truncated mid-write"),
        ('', "empty file"),
        ('not json at all', "garbage"),
    ])
    def test_it_refuses_rather_than_silently_wiping(self, tmp_path, text, label):
        from cura.setup.wizard import write_config
        p = self._corrupt(tmp_path, text)
        before = p.read_text()
        with pytest.raises(RuntimeError):
            write_config(p, {"public_url": "https://x.example.org"})
        assert p.read_text() == before, f"{label}: overwrote an unreadable config"

    def test_the_unreadable_original_is_salvaged(self, tmp_path):
        from cura.setup.wizard import write_config
        p = self._corrupt(tmp_path, '{"twilio": {"auth_token": "secret"} ')
        with pytest.raises(RuntimeError):
            write_config(p, {"public_url": "https://x"})
        salvage = tmp_path / "margaret.unreadable"
        assert salvage.exists() and "secret" in salvage.read_text()

    def test_a_json_array_is_refused_too(self, tmp_path):
        """Valid JSON, wrong shape — {**existing} on a list raises TypeError
        deep inside instead of saying what is wrong."""
        from cura.setup.wizard import write_config
        p = self._corrupt(tmp_path, '["not", "an", "object"]')
        with pytest.raises(RuntimeError):
            write_config(p, {"public_url": "https://x"})

    def test_a_valid_config_still_merges_normally(self, tmp_path):
        import json
        from cura.setup.wizard import write_config
        p = tmp_path / "margaret.json"
        p.write_text(json.dumps({"name": "M", "twilio": {"auth_token": "secret"}}))
        write_config(p, {"public_url": "https://x.example.org"})
        after = json.loads(p.read_text())
        assert after["twilio"]["auth_token"] == "secret"
        assert after["public_url"] == "https://x.example.org"
