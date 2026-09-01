"""Entry point for the double-clickable Cura Setup app.

This is what runs when he double-clicks the thing he downloaded. It is
deliberately not `python -m cura setup --window`: a frozen app has no command
line, and anything that reaches argparse can fail in a way that prints to a
console nobody will ever see.

Three rules for this file:

  1. It must never die silently. A frozen GUI app that raises before the window
     opens shows the user precisely nothing -- the icon bounces once and stops.
     Every path here ends in either a window or a written explanation.
  2. It must not need a terminal, a Python install, or an internet connection.
  3. It must be startable twice. He will double-click it again after being
     interrupted, and that has to land him where he stopped.

`--selftest` exists for CI: it proves the built artifact actually starts, that
Tcl/Tk was collected into the bundle, and that the rehearsal script can be
composed -- without needing a window server on the build runner.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ERROR_LOG = Path.home() / ".cura" / "setup-error.txt"

# What he reads if the app cannot start. No stack trace, no jargon, one action.
CANNOT_START = (
    "Cura's setup window could not open on this computer.\n\n"
    "Nothing you did caused this, and nothing you have already entered is lost.\n\n"
    "What to do next: email the file below to whoever sent you Cura.\n"
    "It says what went wrong.\n\n"
    "    {log}\n"
)


def _selftest() -> int:
    """Prove the bundle is complete. Runs headless; creates no window."""
    import json
    import tempfile

    print("cura-setup selftest")
    print("  frozen:", getattr(sys, "frozen", False))
    print("  python:", sys.version.split()[0])

    import tkinter                      # noqa: F401  loads the bundled Tcl/Tk
    print("  tk:", tkinter.TkVersion)

    from cura.setup import gui
    assert gui.run, "gui.run missing"
    print("  gui module: ok")

    # Compose a real rehearsal from a throwaway config: this walks
    # cura.pulse -> cura.privacy -> cura.sensors -> cura.memory, so a module
    # missing from the bundle fails here rather than in his kitchen.
    from cura.setup.preview import preview_lines
    cfg = {
        "name": "Selftest Person", "preferred_name": "Selftest",
        "phone": "+15555550100",
        "medications": [{"name": "Lisinopril", "time": "morning"}],
        "emergency_contacts": [], "primary_caregiver": {},
        "morning_time": 8, "evening_time": 19,
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(cfg, fh)
        path = fh.name
    lines = preview_lines(path)
    assert lines, "rehearsal produced no lines"
    print(f"  rehearsal: {len(lines)} lines")
    print("SELFTEST OK")
    return 0


# What he reads if a button stops working mid-setup.
CALLBACK_FAILED = (
    "Cura hit a problem on this question and could not go on.\n"
    "\n"
    "Everything you have already answered is saved. Nothing is lost.\n"
    "\n"
    "What to do next: close this window, open Cura Setup again, and use Back\n"
    "to return to the question you were on. If it stops in the same place,\n"
    "send the file below to whoever gave you Cura.\n"
    "\n"
    "    {log}\n"
)


def _install_callback_guard() -> None:
    """Make a failure inside a button do something visible.

    Tkinter catches exceptions raised inside a callback and prints them to
    stderr. In a frozen windowed app there IS no stderr -- so a button that
    fails does nothing at all. He presses Finish, the window sits there, and he
    concludes he did something wrong. He did not.

    Overriding this on the class means it applies to whatever root window
    cura.setup.gui creates, without this file reaching into that module.
    """
    import tkinter as tk
    from tkinter import messagebox

    def handler(self, exc, val, tb):
        detail = "".join(traceback.format_exception(exc, val, tb))
        try:
            ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
            ERROR_LOG.write_text(detail)
        except Exception:
            pass
        try:
            messagebox.showerror("Cura Setup",
                                 CALLBACK_FAILED.format(log=ERROR_LOG))
        except Exception:
            sys.stderr.write(detail)

    tk.Tk.report_callback_exception = handler


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()

    try:
        _install_callback_guard()
    except Exception:
        pass            # never let the safety net be the thing that breaks

    try:
        from cura.setup.gui import run
        return run()
    except Exception:
        detail = traceback.format_exc()
        try:
            ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
            ERROR_LOG.write_text(detail)
        except Exception:
            pass
        message = CANNOT_START.format(log=ERROR_LOG)

        # Try to say it in a window. If tkinter is why we are here, this fails
        # too -- so fall through to stderr rather than raising a second time.
        try:
            import tkinter as tk
            from tkinter import font as tkfont
            root = tk.Tk()
            root.title("Cura Setup")
            root.configure(bg="#FFFFFF")
            root.geometry("720x420")
            f = tkfont.Font(family="Helvetica", size=19)
            tk.Label(root, text=message, font=f, bg="#FFFFFF", fg="#1A1A1A",
                     justify="left", anchor="w", wraplength=640,
                     padx=36, pady=36).pack(fill="both", expand=True)
            tk.Button(root, text="Close", font=f, relief="flat",
                      padx=24, pady=12, command=root.destroy).pack(pady=(0, 28))
            root.mainloop()
        except Exception:
            sys.stderr.write(message)
            sys.stderr.write("\n" + detail)
        return 1


if __name__ == "__main__":
    sys.exit(main())
