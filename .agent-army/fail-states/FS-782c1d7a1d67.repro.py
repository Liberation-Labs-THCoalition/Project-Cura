"""FS-782c1d7a1d67 — a failed check-in call is logged as a sent one.

CuraVoice.call() turns every Twilio failure into CallResult(answered=False,
error=...) and raises nothing. In cura/__main__.py the scheduled jobs await that
call, discard the result, and print "Morning check-in sent to <name>".

So a wrong number, a dead Twilio account or an expired token produces a run that
looks, in the only place anyone can look, exactly like a working one. Nothing
escalates, and the household's single signal that Cura works — the phone
ringing — is the one thing nobody is checking.

RED = call failure is observable in the return value and is discarded, and no
caller consults it.
"""
import ast, asyncio, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cura.comms.voice import CuraVoice

MAIN = ROOT / "cura" / "__main__.py"


def test_call_failure_is_silent_in_the_return_value():
    v = CuraVoice("not-a-sid", "not-a-token", "+15550000000")
    r = asyncio.run(v.call(to_number="", messages=["hello"]))
    assert r.answered is False and r.error, "expected a swallowed failure here"


def _jobs_that_ignore_the_result():
    tree = ast.parse(MAIN.read_text())
    bad = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef):
            continue
        for node in fn.body:
            # `await voice.call(...)` as a bare statement: result thrown away
            if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Await)
                    and isinstance(node.value.value, ast.Call)
                    and getattr(node.value.value.func, "attr", "") == "call"):
                bad.append(f"{fn.name} (line {node.lineno})")
    return bad


def test_scheduled_jobs_check_whether_the_call_connected():
    ignored = _jobs_that_ignore_the_result()
    assert not ignored, (
        "these jobs discard the CallResult and then print 'check-in sent': "
        + ", ".join(ignored)
        + " — a call that never connected is indistinguishable from one that did"
    )
