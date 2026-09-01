"""FS-c1532c191753 — the setup window finishes with no caregiver at all.

cura/setup/wizard.py asks caregiver_name and caregiver_phone as required
questions. cura/setup/gui.py asks the same two with no `required` flag, and
finish() then writes emergency_contacts: [] and primary_caregiver: {} when they
are blank — while the closing screen says "Cura is ready."

Every escalation route reads those two fields. With them empty,
alert_caregiver() dials "" and crisis_alert() iterates nothing.

Tk is not installed in this environment, so gui.run() is driven through a
recording stub for the widget layer only; all validation, state writing and
config building below is gui.py's own code.

RED = a config written by the window with no one to escalate to.
"""
import json, sys, types, pathlib, tempfile, os
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BUTTONS, ENTRIES = [], []


class _W:
    def __init__(self, *a, **kw):
        self._kw = dict(kw); self._children = []
        if a and isinstance(a[0], _W):
            a[0]._children.append(self)
    def pack(self, *a, **k): pass
    pack_configure = pack
    def config(self, **k): self._kw.update(k)
    configure = config
    def cget(self, k): return self._kw.get(k)
    def bind(self, *a, **k): pass
    def unbind(self, *a, **k): pass
    def winfo_exists(self): return 1
    def winfo_width(self): return 800
    def winfo_reqwidth(self): return 820
    def winfo_reqheight(self): return 560
    def winfo_screenwidth(self): return 1920
    def winfo_screenheight(self): return 1080
    def winfo_children(self): return list(self._children)
    def destroy(self): pass
    def focus_set(self): pass
    def update_idletasks(self): pass


class _Entry(_W):
    def __init__(self, *a, **k):
        super().__init__(*a, **k); self._v = ""; ENTRIES.append(self)
    def get(self): return self._v
    def delete(self, *a): self._v = ""
    def insert(self, i, s): self._v += str(s)
    def icursor(self, *a): pass


class _Button(_W):
    def __init__(self, *a, **k):
        super().__init__(*a, **k); BUTTONS.append(self); self._cmd = k.get("command")
    def invoke(self): return self._cmd()


class _Tk(_W):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.tk = types.SimpleNamespace(call=lambda *a: 0)
    def title(self, *a): pass
    def geometry(self, *a): pass
    def minsize(self, *a): pass
    def protocol(self, *a): pass
    def bell(self): pass
    def mainloop(self): pass


class _Font:
    def __init__(self, **k): self._k = k
    def configure(self, **k): self._k.update(k)


def _install_stub_tk():
    tk = types.ModuleType("tkinter")
    for n, c in dict(Tk=_Tk, Frame=_W, Label=_W, Entry=_Entry, Button=_Button,
                     Text=_W, Scrollbar=_W, Toplevel=_W).items():
        setattr(tk, n, c)
    tk.TclError = Exception
    f = types.ModuleType("tkinter.font"); f.Font = _Font
    tk.font = f
    sys.modules["tkinter"] = tk; sys.modules["tkinter.font"] = f
    BUTTONS.clear(); ENTRIES.clear()


def _run_window(answers, home):
    _install_stub_tk()
    import cura.setup.gui as gui
    gui.STATE = pathlib.Path(home) / ".cura" / "setup-progress.json"
    gui.OUT_DIR = pathlib.Path(home) / ".cura"
    gui.run()
    entry = ENTRIES[0]
    nxt = [b for b in BUTTONS if b._kw.get("text") == "Next"][0]
    for a in answers:
        entry._v = a
        nxt.invoke()
    state = json.loads(gui.STATE.read_text())
    return json.loads(pathlib.Path(state["config_path"]).read_text())


def test_window_cannot_finish_without_someone_to_call():
    with tempfile.TemporaryDirectory() as home:
        # Everything answered except the two caregiver questions, which the
        # window presents with nothing marking them as needed.
        cfg = _run_window(
            ["Robert Ellsworth", "", "307-555-0142", "8am", "7pm", "", "", ""],
            home)
    assert cfg["emergency_contacts"], (
        "the window said 'Cura is ready' and wrote a config with no emergency "
        "contact — every escalation has nowhere to go"
    )
    assert cfg["primary_caregiver"].get("phone"), (
        "no primary caregiver phone: alert_caregiver() dials the empty string"
    )
