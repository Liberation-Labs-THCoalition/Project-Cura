import pytest


# --- unbounded retry (2026-09-02: 109 GiB of "Please type an answer") -------

def test_ask_gives_up_instead_of_looping_forever(tmp_path, monkeypatch, capsys):
    """EOF is handled, but an stdin that keeps returning empty lines is not
    EOF — it is an unusable answer, forever. A headless `cura add-phone` sat
    in that loop until it wrote 109 GiB and took the box to ENOSPC."""
    from cura.setup import wizard
    monkeypatch.setattr(wizard, "STATE", tmp_path / "state.json")
    monkeypatch.setattr("builtins.input", lambda *a: "")   # endless empty answers

    with pytest.raises(SystemExit) as e:
        wizard.ask({}, "twilio_sid", "STEP 2 — copy the Account SID here.")
    assert e.value.code == 1

    out = capsys.readouterr().out
    assert out.count("This one is needed") <= wizard.MAX_ATTEMPTS
    assert "stopped" in out.lower()


def test_ask_still_accepts_a_late_answer(tmp_path, monkeypatch):
    """The cap must not truncate a user who fumbles a few times first."""
    from cura.setup import wizard
    monkeypatch.setattr(wizard, "STATE", tmp_path / "state.json")
    answers = iter(["", "", "AC" + "0" * 32])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))

    state = {}
    assert wizard.ask(state, "twilio_sid", "SID?") == "AC" + "0" * 32
    assert state["twilio_sid"] == "AC" + "0" * 32


def test_ask_nothing_is_saved_when_it_gives_up(tmp_path, monkeypatch):
    """Giving up must leave the key unset, so a re-run resumes at the same
    question — the same promise the EOF path makes."""
    from cura.setup import wizard
    monkeypatch.setattr(wizard, "STATE", tmp_path / "state.json")
    monkeypatch.setattr("builtins.input", lambda *a: "")
    state = {}
    with pytest.raises(SystemExit):
        wizard.ask(state, "twilio_sid", "SID?")
    assert "twilio_sid" not in state
