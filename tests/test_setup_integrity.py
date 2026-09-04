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


class TestMeridiemMapping:
    @pytest.mark.parametrize("text,hour24", (
        [(f"{h}am", h) for h in range(1, 12)]          # 1am..11am -> 1..11
        + [("12am", 0)]                                # midnight
        + [(f"{h}pm", h + 12) for h in range(1, 12)]   # 1pm..11pm -> 13..23
        + [("12pm", 12)]                               # noon
        + [(str(h), h) for h in range(24)]             # bare 24h passes through
    ))
    def test_meridiem_lands_in_the_correct_half_of_the_day(self, text, hour24):
        """Mutation survived: `if mer == "pm" and h != 12` became
        `if mer == "am" and h != 12` in to_hour24 — a full meridiem swap.
        Every prior assertion was `0 <= result <= 23`, and a swapped half of
        the day still satisfies that, so the suite stayed green. Under the
        mutation the morning check-in fired at 8pm, the evening check-in at
        7am, and every medication announcement anchored to those hours flipped
        with them: a woman with late-stage dementia called at exactly the
        wrong ends of the day, and nobody calling in the morning at all.
        This pins the whole clock face, not one instance: am is identity with
        12am as 0, pm adds twelve with 12pm staying 12, and bare 24-hour
        input maps to itself."""
        assert to_hour24(text) == hour24


class TestTheWizardGateIsExecutedNotInspected:
    """run() must be EXECUTED to prove the readiness gate points the right way.

    MUTATION THIS CLOSES: wizard.py:438 `if problems:` -> `if not problems:`
    survived the whole suite. The only test of the gate
    (test_the_wizard_gates_its_ready_message) inspects source text for
    'readiness_problems' appearing before the 'All set' string — an inverted
    conditional passes that inspection perfectly, because the check is still
    present in the source; it just points the wrong way. No test ran run().

    What the household would have experienced: a config in which NOBODY CAN BE
    REACHED prints 'All set. Cura is ready.' — the flagship defect this suite
    was built around, resurrected — while a genuinely ready config is told it
    is not ready and sent back through setup, forever.

    Both directions are asserted on a real end-to-end run(): the resume path
    is pre-answered on disk through the wizard's own save(), so the real
    config builder, the real norm_phone, and the real readiness_problems all
    execute. No stub stands in for anything.
    """

    ANSWERS = {
        "name": "Margaret Chen", "preferred_name": "Margaret",
        "phone": "307-555-0134", "morning": "8am", "evening": "7pm",
        "caregiver_name": "Ray", "caregiver_phone": "307-555-0199",
        "can_answer": "yes", "meds": "", "address": "",
    }

    def _run_wizard(self, tmp_path, monkeypatch, capsys, answers):
        import builtins
        from cura.setup import wizard
        monkeypatch.setattr(wizard, "STATE", tmp_path / "setup-progress.json")
        monkeypatch.setattr(wizard, "OUT_DIR", tmp_path)
        monkeypatch.setattr(
            builtins, "input",
            lambda *_a, **_k: pytest.fail(
                "run() asked a question the pre-answered state should cover"))
        wizard.save(dict(answers))   # every question already answered: resume
        wizard.run()
        return capsys.readouterr().out, wizard.load()

    def test_a_genuinely_ready_config_is_told_it_is_ready(
            self, tmp_path, monkeypatch, capsys):
        out, state = self._run_wizard(
            tmp_path, monkeypatch, capsys, self.ANSWERS)
        assert "All set. Cura is ready." in out, \
            "a ready household was refused its ready message"
        assert "not ready" not in out, \
            "a ready household was sent back through setup"
        assert state.get("completed") is True

    def test_a_config_where_nobody_can_be_reached_is_never_told_all_set(
            self, tmp_path, monkeypatch, capsys):
        # "+" is the exact value the historic skipped-question defect stored,
        # and ask() returns stored answers without re-validating — so this
        # reaches the config precisely the way an old state file would.
        out, state = self._run_wizard(
            tmp_path, monkeypatch, capsys,
            {**self.ANSWERS, "caregiver_phone": "+"})
        assert "All set. Cura is ready." not in out, \
            "told a household in which nobody can be reached that Cura is ready"
        assert "not ready yet" in out, \
            "the household was never told what still stops Cura starting"
        assert not state.get("completed"), \
            "setup marked itself completed while nobody can be reached"


class TestEscalationPointsAwayFromThePersonInCrisis:
    """Every escalation destination run() assembles must be the CAREGIVER's
    answer, and the elder's own number must appear in none of them.

    MUTATION THIS CLOSES: wizard.py:418, in run()'s config assembly —
    emergency_contacts built with `"phone": norm_phone(state["phone"])` (the
    elder's own number) instead of `norm_phone(state["caregiver_phone"])`.
    It survived the whole suite: no test executed run()'s config assembly,
    and readiness_problems cannot object because the elder's number is a
    perfectly dialable phone number. Setup says ready, readiness agrees.

    What the household would have experienced: when Cura is worried about
    her, it calls the woman with late-stage dementia herself to summon help
    — she cannot answer a phone — and her husband is never called. The
    escalation path points at the person in crisis.

    The property, not the instance: the test does not merely pin one E.164
    string. It asserts identity through the wizard's own normaliser — every
    escalation phone equals norm_phone(caregiver's raw answer) — and asserts
    the elder's number is absent from every destination, with a guard that
    the two numbers are distinguishable at all. A swap in EITHER direction
    (contacts from the elder, or the elder's line from the caregiver) fails.

    Real objects only: the real ask()/save() resume path pre-answers state on
    disk, then the real run() drives the real norm_phone, write_config and
    readiness_problems. input() is booby-trapped, not stubbed.
    """

    ELDER_RAW = "307-555-0134"       # her line — she cannot answer it
    CAREGIVER_RAW = "(307) 555-0199" # his — deliberately a different format,
                                     # so only norm_phone identity can pass

    ANSWERS = {
        "name": "Margaret Chen", "preferred_name": "Margaret",
        "phone": ELDER_RAW, "morning": "8am", "evening": "7pm",
        "caregiver_name": "Ray", "caregiver_phone": CAREGIVER_RAW,
        "can_answer": "yes", "meds": "", "address": "",
    }

    def _config_run_writes(self, tmp_path, monkeypatch):
        import builtins
        from cura.setup import wizard
        monkeypatch.setattr(wizard, "STATE", tmp_path / "setup-progress.json")
        monkeypatch.setattr(wizard, "OUT_DIR", tmp_path)
        monkeypatch.setattr(
            builtins, "input",
            lambda *_a, **_k: pytest.fail(
                "run() asked a question the pre-answered state should cover"))
        wizard.save(dict(self.ANSWERS))  # every question answered: resume path
        wizard.run()
        return json.loads((tmp_path / "margaret.json").read_text())

    def test_every_escalation_destination_is_the_caregiver_not_the_elder(
            self, tmp_path, monkeypatch):
        cfg = self._config_run_writes(tmp_path, monkeypatch)
        caregiver = norm_phone(self.CAREGIVER_RAW)
        elder = norm_phone(self.ELDER_RAW)
        assert caregiver and elder and caregiver != elder, \
            "test guard: the two numbers must be dialable and distinct, " \
            "or a swap would be invisible"

        destinations = list(cfg["emergency_contacts"]) + [cfg["primary_caregiver"]]
        assert destinations, "no escalation destination was assembled at all"
        for dest in destinations:
            assert dest["phone"] == caregiver, \
                f"escalation destination {dest.get('name', '?')!r} is " \
                f"{dest['phone']!r}, not the caregiver's number — " \
                f"help would be summoned from the wrong phone"
            assert dest["phone"] != elder, \
                "the escalation path points at the person in crisis"
            assert dest["name"] == self.ANSWERS["caregiver_name"]

        # Her own line is still hers — the swap must not exist in the other
        # direction either.
        assert cfg["phone"] == elder

        # Why THIS test has to hold the line: the mutated config is fully
        # dialable, so the readiness gate passes it either way. This assert
        # documents that readiness_problems is not the guard here.
        assert readiness_problems(cfg) == []


class TestARerunAnswerBeatsTheStaleValueOnDisk:
    """Mutation caught: write_config's merge was flipped from
    {**existing, **cfg} to {**cfg, **existing}, reversing precedence so that
    any key already on disk silently beat the freshly-given answer.

    What the household would have experienced: he re-runs setup to correct a
    wrong caregiver number; the wizard accepts it, checks readiness against
    the NEW answers, and prints "All set. Cura is ready." — but the config on
    disk keeps the old wrong number forever. The correction is silently
    discarded, and the number Cura calls when something seems wrong is the
    one he already knows is wrong.

    Why nothing caught it: every earlier merge test used keys that were
    disjoint between the two sides (twilio vs phone/public_url) or identical
    on both (name: Margaret), so precedence was never observable. This test
    pins the property itself: on every overlapping key the new answer wins,
    while keys setup did not author still survive.
    """

    def test_every_overlapping_key_takes_the_new_answer(self, tmp_path):
        out = tmp_path / "margaret.json"
        stale = {
            "name": "Margaret Chen",
            "phone": "+13075550134",
            "primary_caregiver": {"name": "Ray", "phone": "+13075550100"},
            "emergency_contacts": [{"name": "Ray", "phone": "+13075550100",
                                    "relation": "caregiver"}],
            "morning_time": 8,
            "twilio": {"account_sid": "AC1", "auth_token": "secret"},
        }
        out.write_text(json.dumps(stale))

        corrected = {
            "name": "Margaret Chen",
            "phone": "+13075550134",
            "primary_caregiver": {"name": "Ray", "phone": "+13075550199"},
            "emergency_contacts": [{"name": "Ray", "phone": "+13075550199",
                                    "relation": "caregiver"}],
            "morning_time": 9,
        }
        write_config(out, corrected)

        after = json.loads(out.read_text())
        for key, value in corrected.items():
            assert after[key] == value, (
                f"{key}: the re-run's answer was silently discarded in "
                f"favour of the stale value already on disk")
        # Keys setup did not author must still survive the merge.
        assert after["twilio"] == stale["twilio"], \
            "the merge destroyed a block setup did not author"


class TestAnAreaCodeCannotBeginWithZeroOrOne:
    """Mutation caught: wizard.py:156 `or d[1] in "01":` -> `or d[1] in "0":`,
    narrowing the NANP area-code guard so that area codes beginning with 0
    were still refused but ones beginning with 1 slipped straight through.

    What the household would have experienced: a mistyped number like
    1-123-456-7890 is accepted, setup says "All set. Cura is ready", and
    Twilio rejects the number at the moment an escalation call is placed —
    the exact "failure moved to the moment help is needed" the guard's own
    comment warns about. Downstream _dialable is no backstop: its lstrip("1")
    eats the offending area-code digit before it can be seen.

    Why nothing caught it: the bad-number lists covered an area code starting
    with 0 ("0123456789") but never one starting with 1. This class pins the
    PROPERTY — every digit that cannot begin a NANP area code is refused, in
    every way a caregiver might write the number — not one instance of it.
    """

    @pytest.mark.parametrize("bad_first", list("01"))
    @pytest.mark.parametrize("template", [
        "{a}23-456-7890",        # bare ten digits
        "1-{a}23-456-7890",      # with the country code typed out
        "+1 ({a}23) 456-7890",   # E.164-ish, with punctuation
    ])
    def test_no_forbidden_area_code_survives_any_format(self, bad_first, template):
        number = template.format(a=bad_first)
        assert norm_phone(number) == "", (
            f"{number!r} has an area code beginning with {bad_first}, which "
            f"does not exist in the NANP; accepting it moves the failure to "
            f"the moment an escalation call is placed")

    @pytest.mark.parametrize("good_first", list("23456789"))
    def test_every_legal_leading_digit_still_passes(self, good_first):
        # The guard must refuse exactly 0 and 1 — over-refusing would lock a
        # real caregiver number out of setup entirely.
        assert norm_phone(f"{good_first}07-555-0134") == f"+1{good_first}075550134"


class TestTheWindowGateCoversEveryoneCuraMustReach:
    """The window's `required` flag is the ENTIRE readiness gate on the
    packaged double-clickable path — the one a man with failing eyesight
    actually uses. gui.finish() prints "Cura is ready." unconditionally; it
    never calls readiness_problems. The executed gate test above covers only
    wizard.run, so on the window path there is nothing behind the flag.

    MUTATION THIS CLOSES: gui.py questions() — `required=True` dropped from
    the caregiver_phone question. It survived the whole suite because no test
    built questions(state) and asserted which answers the window refuses to
    advance without.

    What the household would have experienced: he presses Next past "The best
    number to reach you?" — one blank screen among eight, easy to do when you
    cannot see the box well — and the window still says "Cura is ready." The
    config it writes holds emergency_contacts: [] and primary_caregiver: {},
    so the first time Cura is worried about her there is nobody on Earth for
    it to call. Every screen before that moment worked; nothing after it can.

    The property, not the instance: every answer the escalation path depends
    on must be forced by the window (readiness_problems refuses a config
    without her name, her number, or a reachable caregiver — pinned by
    TestReadyIsAClaimThatGetsChecked above), and each forced phone number
    must also carry a real dialability check, because `required` alone waves
    "banana" through to norm_phone, which turns it into "" — and the contact
    list is empty again with the flag intact. Real objects throughout: the
    question dicts asserted on here are the very ones go_next consults.
    """

    def _by_key(self):
        from cura.setup.gui import questions
        qs = questions({})
        assert qs, "the window has no questions at all"
        return {q["key"]: q for q in qs}

    @pytest.mark.parametrize("key", ["name", "phone", "caregiver_phone"])
    def test_an_answer_escalation_depends_on_cannot_be_skipped(self, key):
        q = self._by_key()[key]
        assert q.get("required"), (
            f"{key!r} can be skipped in the window, and finish() checks "
            f"nothing afterwards — a blank {key!r} still ends at "
            f"'Cura is ready.' with nobody for Cura to call")

    @pytest.mark.parametrize("key", ["phone", "caregiver_phone"])
    def test_a_forced_number_must_also_be_dialable(self, key):
        q = self._by_key()[key]
        check = q.get("check")
        assert check is not None, (
            f"{key!r} has no validator: any non-empty answer satisfies the "
            f"required gate, norm_phone turns it into '', and the window "
            f"still says 'Cura is ready.'")
        for bad in ("banana", "555", "+"):
            assert check(bad), f"{bad!r} was accepted as a number Cura can dial"
        assert check("307-555-0134") is None, "a real number was refused"
