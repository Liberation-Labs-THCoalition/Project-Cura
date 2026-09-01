"""FS-201dd86b943b — the rehearsal drops the evening check-in in silence.

The rehearsal is the caregiver's only evidence that Cura works. Both renderers
wrap compose_evening in a bare `except Exception: evening = []` and then simply
omit the evening section — cura/__main__.py:170-179 (_preview, the `cura
rehearse` path) and cura/setup/preview.py:32-39 (preview_lines, the setup
window's "Hear a practice call"). _preview then prints "If that sounds right,
you're ready." either way. A caregiver who is shown a morning-only script has
no way to tell a household with no evening medications from an evening
check-in that crashes, and the product tells him he is ready.

The same block is also the divergence preview.py exists to prevent: its own
docstring says both renderers must come from one source, and _preview does not
call preview_lines at all.

RED = a raising compose_evening is swallowed and the caller still reports ready.
"""
import ast, io, json, pathlib, sys, tempfile, contextlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CFG = {
    "name": "Margaret Ellsworth", "preferred_name": "Margaret",
    "phone": "+13075550142", "medications": [{"name": "Donepezil", "time": "morning"}],
    "emergency_contacts": [], "primary_caregiver": {},
    "morning_time": 8, "evening_time": 19,
}


def _config_file():
    d = pathlib.Path(tempfile.mkdtemp())
    p = d / "margaret.json"
    p.write_text(json.dumps(CFG))
    return str(p)


def test_rehearse_does_not_report_ready_when_the_evening_failed():
    import cura.pulse.checkin_composer as cc
    from cura.__main__ import _preview
    original = cc.CheckinComposer.compose_evening
    cc.CheckinComposer.compose_evening = lambda self, *a, **k: (_ for _ in ()).throw(
        RuntimeError("evening composition failed"))
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            _preview(_config_file())
    finally:
        cc.CheckinComposer.compose_evening = original
    out = buf.getvalue()
    assert "In the evening" in out or "you're ready" not in out, (
        "cura rehearse printed no evening check-in and still said "
        "\"If that sounds right, you're ready.\" The caregiver is shown half a "
        "product and told it is whole."
    )


def test_the_two_renderers_are_not_separate_copies():
    src = (ROOT / "cura" / "__main__.py").read_text()
    fn = [n for n in ast.walk(ast.parse(src))
          if isinstance(n, ast.FunctionDef) and n.name == "_preview"][0]
    uses_shared = any(
        (isinstance(n, ast.ImportFrom) and n.module == "cura.setup.preview")
        or (isinstance(n, ast.Call) and getattr(n.func, "id", None) == "preview_lines")
        for n in ast.walk(fn))
    assert uses_shared, (
        "_preview builds the rehearsal itself instead of calling "
        "cura.setup.preview.preview_lines, which that module's docstring says "
        "exists so the terminal and the window cannot drift apart."
    )
