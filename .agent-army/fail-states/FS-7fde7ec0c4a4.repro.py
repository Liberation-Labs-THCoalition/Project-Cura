"""FS-7fde7ec0c4a4 — `cura run` records nothing, so it can never notice anything.

FS-15f837197b69 covers the OUTPUT half: the responder promises to alert the
family and has no callback. This is the INPUT half. `_run_scheduled` builds an
EldercarePulseConfig and then never feeds it anything: record_checkin(),
assess_crisis_level() and add_observation() have no production call site, so
missed_checkins_this_week stays 0, medication_adherence_rate() stays vacuous,
and needs_elevated_monitoring() can never become true. CaregiverSummaryBuilder
is reachable only from cura_mcp_server.py. CuraResponder is imported inside
_run_scheduled and never used.

RED = the escalation machinery has no production caller.
"""
import ast, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PROD = [p for p in (ROOT / "cura").rglob("*.py") if "__pycache__" not in p.parts]


def _call_sites(name):
    hits = []
    for p in PROD:
        try:
            tree = ast.parse(p.read_text())
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                f = n.func
                ident = getattr(f, "attr", None) or getattr(f, "id", None)
                if ident == name:
                    hits.append(f"{p.relative_to(ROOT)}:{n.lineno}")
    return hits


def test_checkin_results_are_recorded_somewhere():
    assert _call_sites("record_checkin"), (
        "record_checkin() has no call site in cura/. Every scheduled call's "
        "outcome is dropped, so missed_checkins_this_week never leaves 0 and "
        "needs_elevated_monitoring() can never fire."
    )


def test_something_assesses_crisis_level():
    assert _call_sites("assess_crisis_level"), (
        "assess_crisis_level() has no call site in cura/. Nothing in the "
        "shipped product ever decides that a caregiver should be told."
    )


def test_run_scheduled_uses_the_responder_it_imports():
    src = (ROOT / "cura" / "__main__.py").read_text()
    fn = [n for n in ast.walk(ast.parse(src))
          if isinstance(n, ast.FunctionDef) and n.name == "_run_scheduled"][0]
    imported = any(
        isinstance(n, ast.ImportFrom) and any(a.name == "CuraResponder" for a in n.names)
        for n in ast.walk(fn))
    used = any(isinstance(n, ast.Call) and getattr(n.func, "id", None) == "CuraResponder"
               for n in ast.walk(fn))
    assert not (imported and not used), (
        "_run_scheduled imports CuraResponder and never constructs it. "
        "Nothing in the daily run can receive a keypad press or a spoken word."
    )
