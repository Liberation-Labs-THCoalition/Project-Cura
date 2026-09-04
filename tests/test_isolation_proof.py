"""Prove the isolation fixture isolates, rather than trusting that it does."""
from pathlib import Path


def test_home_is_not_the_real_one():
    import os
    assert "/home/asdf" != str(Path.home()), "tests are running in the real home"
    assert str(Path.home()) == os.environ["HOME"]


def test_writing_a_pending_question_does_not_touch_the_real_home(tmp_path):
    from datetime import datetime, timezone
    from cura.comms.pending import PENDING_FILE, save_pending
    save_pending("home_safety", datetime.now(timezone.utc))
    assert PENDING_FILE.exists()
    assert not str(PENDING_FILE).startswith("/home/asdf/.cura"), \
        "the pending file landed in the developer's real ~/.cura"


def test_every_captured_home_path_is_isolated():
    """Monkeypatching Path.home() does not move a path captured at import.

    The fixture looked like it isolated everything while wizard.STATE still
    pointed at the developer's real ~/.cura. A fixture that does not isolate is
    indistinguishable from one that does, until something leaks — so this
    asserts it rather than assuming it."""
    import cura.setup.wizard as wiz
    from cura.comms import pending
    for label, value in (("wizard.STATE", wiz.STATE),
                         ("wizard.OUT_DIR", wiz.OUT_DIR),
                         ("pending.PENDING_FILE", pending.PENDING_FILE)):
        assert not str(value).startswith("/home/asdf/.cura"), \
            f"{label} still points at the real home: {value}"


def test_the_wizard_writes_into_the_isolated_home():
    """The end the assertion above is for: a real write must not escape."""
    import cura.setup.wizard as wiz
    wiz.save({"probe": "x"})
    assert Path(wiz.STATE).exists()
    assert not Path("/home/asdf/.cura/setup-progress.json").read_text() \
        .startswith('{"probe"') if Path("/home/asdf/.cura/setup-progress.json").exists() else True
