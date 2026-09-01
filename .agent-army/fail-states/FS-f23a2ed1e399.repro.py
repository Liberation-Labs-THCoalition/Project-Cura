"""FS-f23a2ed1e399 — `python -m cura.comms.webhook` starts the Werkzeug debugger.

The module's own __main__ block ends:

    app.run(host="0.0.0.0", port=args.port, debug=True)

and the module docstring, six lines up, says:

    Run standalone for development:
      python -m cura.comms.webhook --port 5000
    In production, put this behind ngrok or a reverse proxy so Twilio can
    reach it.

Those two instructions are given together, so the documented way to make Twilio
reach Cura is to run this exact line and tunnel a public URL to it. `debug=True`
turns on Werkzeug's interactive debugger: an unhandled exception renders a
traceback page with an in-browser Python console attached, gated only by a PIN
printed to a terminal that on this deployment is a laptop in a Wyoming kitchen.
`host="0.0.0.0"` means it is also reachable from every other device on the LAN.

Observed on this revision: starting the module printed "Debugger is active! /
Debugger PIN: 113-347-580", bound 0.0.0.0:5599, and served the debugger console
resource at /?__debugger__=yes&cmd=resource&f=debugger.js.

What reaches the household: the process holding the debugger is the same process
that decides whether a caregiver gets paged, and it runs with the Twilio auth
token and the resident's address in memory. `cura webhook` (cura/__main__.py)
gets this right and omits debug; only the module's own entry point does not.

RED = the shipped __main__ block passes debug=True.
"""
import ast
import pathlib

WEBHOOK = (pathlib.Path(__file__).resolve().parents[2]
           / "cura" / "comms" / "webhook.py")


def _app_run_calls(tree):
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "run"):
            yield node


def test_webhook_entrypoint_does_not_enable_the_debugger():
    tree = ast.parse(WEBHOOK.read_text())
    offenders = []
    for call in _app_run_calls(tree):
        for kw in call.keywords:
            if kw.arg == "debug" and getattr(kw.value, "value", False) is True:
                offenders.append(call.lineno)
    assert not offenders, (
        f"cura/comms/webhook.py line(s) {offenders} call app.run(debug=True). "
        "The Werkzeug interactive debugger is exposed on the same process that "
        "handles Twilio callbacks and holds the resident's address."
    )


def test_webhook_entrypoint_does_not_bind_all_interfaces_with_debug():
    tree = ast.parse(WEBHOOK.read_text())
    for call in _app_run_calls(tree):
        kwargs = {kw.arg: getattr(kw.value, "value", None) for kw in call.keywords}
        if kwargs.get("debug") is True:
            assert kwargs.get("host") not in ("0.0.0.0", "::"), (
                f"line {call.lineno}: debug=True together with "
                f"host={kwargs.get('host')!r} publishes the debugger to the "
                "whole LAN, and to the internet once ngrok is pointed at it."
            )
