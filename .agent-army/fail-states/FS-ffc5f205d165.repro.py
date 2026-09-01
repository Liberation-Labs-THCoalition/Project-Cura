"""FS-ffc5f205d165 — unknown_timing_medications() is never called.

medication_slots() deliberately returns the empty set for any timing it cannot
read, so the medication is never spoken aloud. Its docstring says the caregiver
"must be told this list", and unknown_timing_medications() exists to produce it.
Nothing in cura/ calls it. The medication is dropped in silence.

RED = the helper has no call site in the shipped product.
"""
import re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cura.pulse.eldercare_pulse import unknown_timing_medications, medication_slots


def _call_sites():
    hits = []
    for p in (ROOT / "cura").rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        for n, line in enumerate(p.read_text().splitlines(), 1):
            if "unknown_timing_medications" not in line:
                continue
            if p.name == "eldercare_pulse.py" and (
                re.search(r"^\s*def unknown_timing_medications", line)
                or "`unknown_timing_medications`" in line):
                continue          # the definition and its own docstring
            hits.append(f"{p.relative_to(ROOT)}:{n}")
    return hits


def test_unreadable_timing_is_actually_dropped():
    for t in ("with lunch", "as needed", "PRN", "noon", "after meals", ""):
        assert medication_slots({"name": "Warfarin", "time": t}) == set()
    assert unknown_timing_medications(
        [{"name": "Warfarin", "time": "with lunch"}]) == ["Warfarin"]


def test_caregiver_is_told_which_medications_were_dropped():
    sites = _call_sites()
    assert sites, (
        "unknown_timing_medications() has no call site in cura/. Medications "
        "Cura cannot time are omitted from every check-in and nobody is told, "
        "so the caregiver assumes they are being covered."
    )
