"""FS-2523bb0a6b27 — the Twilio auth token is stored world-readable.

`cura add-phone` calls wizard.ask(), and ask() calls wizard.save() after every
answer. So the Account SID and the Auth Token land in

    ~/.cura/setup-progress.json

alongside the resident's home address, medication list, her phone number and the
caregiver's. save() never chmods that file, and never chmods ~/.cura either, so
both take the process umask: 0644 / 0755 on a normal desktop.

add_phone.py DOES chmod the derived config to 0600, with the comment
"# the auth token lives here now". It lives in two places. Only one is locked.

What reaches the household: a Twilio Account SID + Auth Token is full control of
the account. Anyone who reads that file -- another account on the machine, a
support tech, or anyone with a copy of a home backup, since ~/.cura is inside the
home directory every backup tool sweeps -- can place calls FROM Cura's number.
That is the number a woman with late-stage dementia has been taught to trust.
They also get her address.

RED = a file containing the auth token is readable by group or other.
"""
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

TOKEN = "abcdef0123456789abcdef0123456789"


def _run_setup_then_add_phone(home: pathlib.Path):
    """Drive the real wizard + add-phone flows against a throwaway HOME."""
    import builtins
    import importlib

    os.environ["HOME"] = str(home)
    for mod in ("cura.setup.wizard", "cura.setup.add_phone"):
        sys.modules.pop(mod, None)
    wizard = importlib.import_module("cura.setup.wizard")
    add_phone = importlib.import_module("cura.setup.add_phone")

    real_input = builtins.input
    answers = iter([
        "Margaret Chen", "Margaret", "555-123-4567", "8am", "7pm",
        "Walter Chen", "555-987-6543", "Lisinopril, Metformin",
        "412 County Road 14, Buffalo, Wyoming",
        "",                                   # Enter after the Twilio signup step
        "AC" + "1" * 32, TOKEN, "+13075550142",
    ])
    builtins.input = lambda prompt="": next(answers)
    try:
        wizard.run()
        add_phone.run()
    finally:
        builtins.input = real_input
    return wizard.STATE


def test_no_file_holding_the_auth_token_is_world_readable():
    with tempfile.TemporaryDirectory() as td:
        home = pathlib.Path(td)
        _run_setup_then_add_phone(home)

        cura_dir = home / ".cura"
        leaks = []
        for path in sorted(cura_dir.rglob("*")):
            if not path.is_file():
                continue
            try:
                text = path.read_text()
            except Exception:
                continue
            if TOKEN not in text:
                continue
            mode = path.stat().st_mode & 0o777
            if mode & 0o077:
                leaks.append((path.name, oct(mode)))

        assert not leaks, (
            "the Twilio auth token is readable by other accounts and by every "
            f"home-directory backup: {leaks}. "
            "add_phone.py chmods the config to 0600 but wizard.save() leaves "
            "setup-progress.json -- which holds the same token plus the "
            "resident's address and medication list -- at the umask default."
        )


def test_cura_directory_is_not_world_traversable():
    with tempfile.TemporaryDirectory() as td:
        home = pathlib.Path(td)
        _run_setup_then_add_phone(home)
        mode = (home / ".cura").stat().st_mode & 0o777
        assert not (mode & 0o077), (
            f"~/.cura is {oct(mode)}; it should be 0700. Every other account on "
            "the machine can list and read the resident's care file."
        )
