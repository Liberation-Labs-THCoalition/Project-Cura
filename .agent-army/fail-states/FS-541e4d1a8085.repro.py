"""FS-541e4d1a8085 — the setup window is a dead end: it never turns calls on.

install.sh advertises "Cura's setup window", and the .app/.exe is meant to open
`cura setup --window`. That window's finish() screen says "Cura is ready.",
offers "Hear a practice call" and "Close", and stops. It never names
`cura add-phone` (without which CuraVoice has no credentials and dials nobody)
and never names `cura run` (without which nothing is ever scheduled). The
terminal wizard prints both; the window prints neither.

So a caregiver who installs by the advertised route completes setup, hears a
rehearsal, closes the window, and the phone never rings — having been told on
screen that Cura is ready.

RED = gui.py's finishing screen mentions no route to real phone calls, while
wizard.py's does.
"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GUI = ROOT / "cura" / "setup" / "gui.py"
WIZ = ROOT / "cura" / "setup" / "wizard.py"

NEXT_STEPS = ("add-phone", "add_phone", "cura run")


def _mentions(path):
    if not path.exists():
        return None
    text = path.read_text()
    return [s for s in NEXT_STEPS if s in text]


def test_terminal_wizard_names_the_next_steps():
    """Control: the terminal path does tell him. This is the shape gui.py lacks."""
    assert _mentions(WIZ), "wizard.py names no next step either; premise changed"


def test_window_tells_him_how_to_turn_real_calls_on():
    found = _mentions(GUI)
    assert found is not None, "cura/setup/gui.py is missing"
    assert found, (
        "The setup window's ending mentions none of add-phone or 'cura run'. "
        "It says \"Cura is ready.\" and offers only a practice call and Close, "
        "so the household that installs by the advertised route never gets a "
        "real phone call and is told nothing is missing."
    )
