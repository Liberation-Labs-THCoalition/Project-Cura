"""Test isolation.

Cura reads and writes ~/.cura — configs, the dose ledger, memory, and now the
pending-question file that lets `cura webhook` answer a question `cura run`
asked. All of that is correct in production and wrong in a test run: a stray
file left by a manual verification made test_general_conversation fail, because
a freshly constructed responder read the real user's pending question and
treated an unrelated sentence as an answer to it.

That is the same defect as this morning's alert leaking into Ember's inbox, in
the other direction — there I did not consider where a test's artifacts LANDED,
here I did not consider where a test READS FROM. Both are "the check works and
its surroundings were not thought about."

So: every test gets its own HOME. No test can see the developer's real state,
and no test can leave anything in it.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".cura").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: home))

    # Modules that captured a path AT IMPORT TIME need repointing individually.
    # Monkeypatching Path.home() does not move them, so the fixture looked like
    # it isolated everything while cura/setup/wizard.py still wrote the real
    # ~/.cura/setup-progress.json. Caught by a test that asserts the isolation
    # rather than assuming it — a fixture that does not isolate is
    # indistinguishable from one that does, until something leaks.
    cura_dir = home / ".cura"
    CAPTURED = [
        ("cura.comms.pending", "PENDING_FILE", cura_dir / "pending_question.json"),
        ("cura.setup.wizard", "STATE", cura_dir / "setup-progress.json"),
        ("cura.setup.wizard", "OUT_DIR", cura_dir),
        ("cura.setup.gui", "STATE", cura_dir / "setup-progress.json"),
        ("cura.setup.gui", "OUT_DIR", cura_dir),
    ]
    import importlib
    for module_name, attr, value in CAPTURED:
        try:
            mod = importlib.import_module(module_name)
        except Exception:
            continue          # tkinter-less environments cannot import gui
        if hasattr(mod, attr):
            monkeypatch.setattr(mod, attr, value)
    yield home
