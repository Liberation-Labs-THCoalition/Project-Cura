"""FS-01b7dacc128d — in production Cura has no memory and no wearable.

CheckinComposer takes `memory` and `wearable_analyzer`. Every production
construction (cura/__main__.py:159 rehearse, :239 the daily run) passes
neither, so _memory_touches() returns [] on every call and
wearable_observations is always []. The docstring on _memory_touches calls
these "the human touches that make Cura a companion". They never happen, and
nothing the wearable sees ever reaches a check-in or a caregiver.

RED = the shipped check-in path constructs CheckinComposer with no memory and
no wearable analyzer, and the composed check-in contains no memory touch even
when the memory holds an unreferenced event.
"""
import ast, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cura.pulse.checkin_composer import CheckinComposer
from cura.pulse.eldercare_pulse import ElderProfile, EldercarePulseConfig
from cura.memory.companion_memory import CompanionMemory


def _composer_constructions():
    src = (ROOT / "cura" / "__main__.py").read_text()
    out = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "CheckinComposer":
            out.append((n.lineno, sorted(k.arg for k in n.keywords), len(n.args)))
    return out


def test_production_composer_is_given_a_memory():
    calls = _composer_constructions()
    assert calls, "no CheckinComposer construction found in cura/__main__.py"
    bare = [c for c in calls if not c[1] and not c[2]]
    assert not bare, (
        f"CheckinComposer built with no memory and no wearable at "
        f"cura/__main__.py lines {[c[0] for c in bare]}. Cura remembers nothing "
        f"between calls and nothing the wearable sees reaches the household."
    )


def test_a_remembered_event_reaches_the_morning_checkin():
    """The capability exists; the shipped wiring does not use it."""
    mem = CompanionMemory(elder_name="Margaret")
    mem.add_event("her granddaughter's wedding", date="2026-09-20", people=["Sarah"])
    profile = ElderProfile(name="Margaret Ellsworth", preferred_name="Margaret")
    cfg = EldercarePulseConfig(profile)

    wired = CheckinComposer(memory=mem).compose_morning(cfg).all_messages
    assert any("wedding" in m for m in wired), (
        "the memory path itself is broken, not just unwired")

    shipped = CheckinComposer().compose_morning(cfg).all_messages   # as cura run builds it
    assert any("wedding" in m for m in shipped), (
        "The check-in cura run actually speaks contains no memory touch. "
        "Cura greets her as a stranger every morning."
    )
