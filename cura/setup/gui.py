"""Cura setup — a window, not a terminal.

The person setting this up is often in their seventies or eighties, caring for a
spouse, with failing eyesight. Asking them to open a terminal is where setup ends.
This is a double-clickable window instead.

Deliberate choices, each from a constraint rather than taste:

  - 20pt body text, 26pt questions, and a "Bigger text" button that goes up to
    32pt body / 38pt question and is remembered between sessions. 20pt clears the
    large-print threshold; failing eyesight in the seventies often does not stop
    there, and the answer to "is it big enough" has to be his, not ours.
  - The window sizes itself to its own content. A hard-coded window is fine at
    100% system text size and drops the Back and Next buttons off the bottom edge
    at 150% — which is exactly the setting someone with failing eyesight has
    already turned on.
  - One question per screen. A form with nine fields is nine chances to lose
    your place; a screen with one question has none.
  - Progress saved on every Next, and the half-typed answer saved on close too.
    Interruption is the normal case here, not the edge case: reopen and it
    returns to the same question with the same words still in the box.
  - Back always available. People check their own answers, and being unable to
    is what makes software feel hostile.
  - No progress bar percentage, no spinner, no jargon, no icons-as-meaning.
  - Errors appear beside the question in plain words, never in a dialog box that
    has to be dismissed before you can see what you typed.
  - Nothing is ever required except a name and a phone number. Everything else
    can be skipped and added later, because a stuck field ends the session.

Contrast, measured rather than eyeballed (WCAG 2.2 AA wants 4.5:1 for text and
3:1 for the edges of controls and for focus rings):

    #1A1A1A on #FFFFFF  17.4:1   body and question text
    #444444 on #FFFFFF   9.7:1   help text and "Question 3 of 8"
    #8A1C1C on #FFFFFF   9.3:1   error text (never the only signal — it is words)
    #FFFFFF on #1F5C3A   7.9:1   the Next button
    #595959 on #FFFFFF   7.0:1   the edge of the answer box
    #1A1A1A on #FFFFFF  17.4:1   the focus ring
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

STATE = Path.home() / ".cura" / "setup-progress.json"
OUT_DIR = Path.home() / ".cura"

BG = "#FFFFFF"
FG = "#1A1A1A"
ACCENT = "#1F5C3A"      # dark green: passes contrast on white, not red/green coded
MUTED = "#444444"
ERR = "#8A1C1C"
EDGE = "#595959"        # 7.0:1 on white — the answer box needs a visible edge,
                        # and the old #BBBBBB was 1.9:1, under the 3:1 floor
FIELD = "#F4F4F4"
BACK_FILL = "#DCDCDC"   # "Back" needs a fill you can find; #d9d9d9 default was
                        # 1.4:1 against the window and effectively invisible

# One press of "Bigger text" adds this many points to everything.
ZOOM_STEP = 3
ZOOM_MAX = 4
BASE_SIZES = dict(q=26, body=20, help=17, btn=19)

# Two Returns inside this many milliseconds is a bounced key or a held key,
# not two decisions. Questions with a default already in the box would
# otherwise be answered by a keystroke he did not mean to make twice.
ENTER_GUARD_MS = 600



def _parse_meds(raw):
    """Keep the timing the caregiver wrote instead of inventing "morning".

    Same fix as the terminal wizard: an invented timing is announced as fact,
    and a fabricated "morning" turns an as-needed opioid into a daily prompt.
    """
    from cura.pulse.medication import parse_medication_list, split_medication
    if isinstance(raw, str):
        return parse_medication_list(raw)
    return [split_medication(m) if isinstance(m, str) else m for m in (raw or [])]


def _load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def _save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(STATE.parent, 0o700)
    except OSError:
        pass
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    try:
        os.chmod(tmp, 0o600)   # before the rename: no window at the final path
    except OSError:
        pass
    os.replace(tmp, STATE)


def _phone_ok(v):
    d = re.sub(r"\D", "", v)
    return None if len(d) in (10, 11) else \
        "That doesn't look like a full phone number. Any format is fine — 555-123-4567 works."


def _norm_phone(v):
    d = re.sub(r"\D", "", v)
    return "+" + ("1" + d if len(d) == 10 else d)


# One validator serves both wizards. The terminal wizard accepts a bare
# hour like "8" (am/pm optional) and saves it to the SHARED state file;
# a stricter regex here crashed _to24 on resume (FS-1). Import, don't copy.
from cura.setup.wizard import an_hour as _hour_ok, to_hour24 as _to24


def questions(state):
    """Built fresh each time so later questions can use earlier answers."""
    first = (state.get("name") or "them").split()[0]
    return [
        dict(key="name", q="Who will Cura be calling?",
             help="Their first and last name.", required=True),
        dict(key="preferred_name", q=f"What does {first} like to be called?",
             help="This is what Cura says on the phone.", default=first),
        dict(key="phone", q=f"What number should Cura call to reach {first}?",
             help="A landline is perfectly fine.", required=True, check=_phone_ok),
        dict(key="morning", q=f"When does {first} usually start the day?",
             help="Cura calls to say good morning around then.",
             default="8am", check=_hour_ok),
        dict(key="evening", q=f"When does {first} settle in for the evening?",
             help="Cura checks in again then.", default="7pm", check=_hour_ok),
        dict(key="caregiver_name", q="And what is your name?",
             help="If Cura is ever worried, this is who it tells."),
        dict(key="caregiver_phone", q="The best number to reach you?",
             help="Cura will contact you if something seems wrong.", check=_phone_ok),
        dict(key="meds", q=f"Does {first} take any regular medications?",
             help="Separate them with commas, like: Lisinopril, Metformin. "
                  "Don't worry about doses. You can leave this empty."),
    ]


def _no_window_message() -> str:
    return (
        "Cura could not open its setup window.\n"
        "\n"
        "This is not something you did wrong. This computer's copy of Python is\n"
        "missing the small extra piece that draws windows.\n"
        "\n"
        "ONE THING TO DO: ask whoever helps you with this computer to install the\n"
        "piece called \"Tk\". On Ubuntu or Debian that is the package python3-tk.\n"
        "It takes them about a minute, and then Cura's setup window will open when\n"
        "you double-click it again.\n"
        "\n"
        "Nothing you have already answered is lost.\n"
    )


def _button(tk, parent, text, command, font, primary=False):
    """A button you can see the edge of, and see the focus on.

    The old buttons carried Tk's 1px black focus ring. On the green Next button
    that ring is 2.65:1 — under the 3:1 floor and one pixel wide, so keyboard
    focus was effectively invisible. Here the ring is 3px of #1A1A1A on the white
    window (17.4:1), and it appears where there was no ring at all, so the cue is
    "a ring arrived", not "a colour shifted slightly".
    """
    opts = dict(text=text, command=command, font=font,
                bd=2, relief="solid", padx=(34 if primary else 24), pady=14,
                highlightthickness=3, highlightbackground=BG, highlightcolor=FG,
                takefocus=True)
    if not primary:
        return tk.Button(parent, bg=BACK_FILL, fg=FG, activebackground="#C8C8C8",
                         activeforeground=FG, disabledforeground=MUTED, **opts)
    if sys.platform == "darwin":
        # macOS draws native buttons and ignores `bg`, which would leave white
        # text on a light grey button. Colour the text instead.
        return tk.Button(parent, fg=ACCENT, activeforeground=ACCENT,
                         highlightbackground=ACCENT, **opts)
    return tk.Button(parent, bg=ACCENT, fg="white", activebackground="#17472C",
                     activeforeground="white", **opts)


def run() -> int:
    try:
        import tkinter as tk
        from tkinter import font as tkfont
    except Exception:
        msg = _no_window_message()
        print(msg)
        # He has no terminal, so printing is not telling him. Leave the note
        # somewhere he will actually find it.
        for spot in (Path.home() / "Desktop", Path.home()):
            try:
                (spot / "Cura - please read.txt").write_text(msg)
                break
            except Exception:
                continue
        return 2

    state = _load()
    root = tk.Tk()
    root.title("Cura Setup")
    root.configure(bg=BG)

    zoom = [max(0, min(ZOOM_MAX, int(state.get("text_size", 0) or 0)))]
    f_q = tkfont.Font(family="Helvetica", size=BASE_SIZES["q"])
    f_body = tkfont.Font(family="Helvetica", size=BASE_SIZES["body"])
    f_help = tkfont.Font(family="Helvetica", size=BASE_SIZES["help"])
    f_btn = tkfont.Font(family="Helvetica", size=BASE_SIZES["btn"])
    FONTS = {"q": f_q, "body": f_body, "help": f_help, "btn": f_btn}

    def apply_zoom():
        for name, f in FONTS.items():
            f.configure(size=BASE_SIZES[name] + ZOOM_STEP * zoom[0])
        smaller_btn.config(state=("normal" if zoom[0] > 0 else "disabled"))
        bigger_btn.config(state=("normal" if zoom[0] < ZOOM_MAX else "disabled"))
        fit()

    def bump(delta):
        zoom[0] = max(0, min(ZOOM_MAX, zoom[0] + delta))
        state["text_size"] = zoom[0]
        _save(state)
        apply_zoom()

    idx = [0]
    qs = [questions(state)]
    seen = [820, 560]          # the window only ever grows, so it never twitches

    wrap = tk.Frame(root, bg=BG, padx=48, pady=40)
    wrap.pack(fill="both", expand=True)

    topbar = tk.Frame(wrap, bg=BG)
    step = tk.Label(wrap, text="", font=f_body, bg=BG, fg=MUTED, anchor="w")
    qlabel = tk.Label(wrap, text="", font=f_q, bg=BG, fg=FG,
                      anchor="w", justify="left", wraplength=700)
    hlabel = tk.Label(wrap, text="", font=f_help, bg=BG, fg=MUTED,
                      anchor="w", justify="left", wraplength=700)
    entry = tk.Entry(wrap, font=f_body, bg=FIELD, fg=FG,
                     relief="flat", insertwidth=3, insertbackground=FG,
                     highlightthickness=3, highlightbackground=EDGE,
                     highlightcolor=ACCENT)
    elabel = tk.Label(wrap, text="", font=f_help, bg=BG, fg=ERR,
                      anchor="w", justify="left", wraplength=700)
    row = tk.Frame(wrap, bg=BG)

    # Packed bottom-first on purpose. Tk's packer hands out space in packing
    # order, so whatever is packed last is what gets squeezed when the window is
    # short. Packing the buttons first means a cramped window loses help text,
    # never the way forward.
    row.pack(side="bottom", fill="x", pady=(28, 0))
    topbar.pack(side="top", fill="x")
    step.pack(fill="x")
    qlabel.pack(fill="x", pady=(18, 10))
    hlabel.pack(fill="x", pady=(0, 18))
    entry.pack(fill="x", ipady=14)
    elabel.pack(fill="x", pady=(10, 0))
    topbar.pack_configure(before=step)

    def fit():
        """Grow the window to whatever the text actually needs.

        At 150% system text scaling the old fixed 820x560 window needed 589px of
        content, and at 200% it needed 750px — the button row collapsed to one
        pixel and Next stopped being drawn at all.
        """
        root.update_idletasks()
        w = max(seen[0], root.winfo_reqwidth())
        h = max(seen[1], root.winfo_reqheight())
        w = min(w, max(400, root.winfo_screenwidth() - 80))
        h = min(h, max(300, root.winfo_screenheight() - 140))
        seen[0], seen[1] = w, h
        root.geometry(f"{w}x{h}")
        root.minsize(min(700, w), min(420, h))

    def rewrap(_e=None):
        avail = max(280, wrap.winfo_width() - 2 * 48)
        for lab in (qlabel, hlabel, elabel):
            if lab.winfo_exists() and lab.cget("wraplength") != avail:
                lab.config(wraplength=avail)
    wrap.bind("<Configure>", rewrap)

    def draft_get(key):
        return (state.get("_typing") or {}).get(key)

    def draft_clear():
        if state.pop("_typing", None) is not None:
            _save(state)

    def draw():
        qs[0] = questions(state)
        q = qs[0][idx[0]]
        step.config(text=f"Question {idx[0] + 1} of {len(qs[0])}")
        qlabel.config(text=q["q"])
        hlabel.config(text=q.get("help", ""))
        elabel.config(text="")
        entry.delete(0, "end")
        # A half-typed answer from a session that got interrupted outranks both
        # the saved answer and the default — it is the most recent thing he said.
        shown = draft_get(q["key"])
        if shown is None:
            shown = state.get(q["key"], q.get("default", ""))
        entry.insert(0, shown)
        entry.icursor("end")
        entry.focus_set()
        back_btn.config(state=("normal" if idx[0] > 0 else "disabled"))
        next_btn.config(text=("Finish" if idx[0] == len(qs[0]) - 1 else "Next"))
        fit()

    last_enter = [0]

    def go_next(_event=None):
        if _event is not None:
            now = root.tk.call("clock", "milliseconds")
            if now - last_enter[0] < ENTER_GUARD_MS:
                return "break"      # bounced or held key, not a second answer
            last_enter[0] = now
        q = qs[0][idx[0]]
        val = entry.get().strip()
        if not val and q.get("required"):
            elabel.config(text="This one is needed to make the call.")
            root.bell()
            fit()
            return "break"
        if val and q.get("check"):
            problem = q["check"](val)
            if problem:
                elabel.config(text=problem)
                root.bell()
                fit()
                return "break"
        state[q["key"]] = val
        state.pop("_typing", None)   # answered, so there is no draft any more
        _save(state)                 # saved before advancing, always
        if idx[0] == len(qs[0]) - 1:
            finish()
            return "break"
        idx[0] += 1
        draw()
        return "break"

    def go_back():
        if idx[0] > 0:
            state.pop("_typing", None)
            _save(state)
            idx[0] -= 1
            draw()

    def on_close():
        """Closing is not cancelling. Keep what is in the box."""
        try:
            if entry.winfo_exists():
                typed = entry.get()
                key = qs[0][idx[0]]["key"]
                if typed.strip() and typed.strip() != state.get(key):
                    state["_typing"] = {key: typed}
                else:
                    state.pop("_typing", None)
                _save(state)
        except Exception:
            pass
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)

    def finish():
        draft_clear()
        meds = [m.strip() for m in (state.get("meds") or "").split(",") if m.strip()]
        cfg = {
            "name": state["name"],
            "preferred_name": state.get("preferred_name") or state["name"].split()[0],
            "phone": _norm_phone(state["phone"]),
            "medications": _parse_meds(meds),
            "emergency_contacts": ([{"name": state.get("caregiver_name", ""),
                                     "phone": _norm_phone(state["caregiver_phone"]),
                                     "relation": "caregiver"}]
                                   if state.get("caregiver_phone") else []),
            "primary_caregiver": ({"name": state.get("caregiver_name", ""),
                                   "phone": _norm_phone(state["caregiver_phone"])}
                                  if state.get("caregiver_phone") else {}),
            "morning_time": _to24(state.get("morning", "8am")),
            "evening_time": _to24(state.get("evening", "7pm")),
        }
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^a-z0-9]+", "-", cfg["preferred_name"].lower()).strip("-") or "person"
        out = OUT_DIR / f"{safe}.json"
        out.write_text(json.dumps(cfg, indent=2))
        try:
            out.chmod(0o600)  # address, numbers, medication list
        except OSError:
            pass
        state["completed"] = True
        state["config_path"] = str(out)
        _save(state)

        # The Return keys were aimed at a question box that is about to stop
        # existing. Leaving them bound made every later Enter raise TclError
        # into a terminal he cannot see.
        for seq in ("<Return>", "<KP_Enter>"):
            root.unbind(seq)
        wrap.unbind("<Configure>")
        root.protocol("WM_DELETE_WINDOW", root.destroy)

        for w in wrap.winfo_children():
            w.destroy()
        who = cfg["preferred_name"]
        tk.Label(wrap, text="Cura is ready.", font=f_q, bg=BG, fg=ACCENT,
                 anchor="w", justify="left").pack(fill="x", pady=(30, 20))
        tk.Label(wrap, text=f"Everything is set up for {who}.\n\n"
                            "Next, listen to a practice call so you can hear exactly\n"
                            f"what {who} will hear. Nothing is dialled.",
                 font=f_body, bg=BG, fg=FG, anchor="w",
                 justify="left").pack(fill="x")
        b = tk.Frame(wrap, bg=BG)
        b.pack(side="bottom", fill="x", pady=(30, 0))
        hear = _button(tk, b, "Hear a practice call",
                       lambda: _rehearse_window(root, out, f_body, f_q, f_btn),
                       f_btn, primary=True)
        hear.pack(side="right")
        _button(tk, b, "Close", root.destroy, f_btn).pack(side="right", padx=(0, 12))
        hear.focus_set()
        for seq in ("<Return>", "<KP_Enter>"):
            root.bind(seq, lambda e: (hear.invoke(), "break")[1])
        fit()

    back_btn = _button(tk, row, "Back", go_back, f_btn)
    back_btn.pack(side="left")
    next_btn = _button(tk, row, "Next", go_next, f_btn, primary=True)
    next_btn.pack(side="right")

    # Created last so keyboard travel is answer box -> Back -> Next -> text size,
    # while `before=step` keeps them drawn at the top of the window.
    bigger_btn = _button(tk, topbar, "Bigger text", lambda: bump(+1), f_help)
    smaller_btn = _button(tk, topbar, "Smaller text", lambda: bump(-1), f_help)
    smaller_btn.pack(side="right", padx=(10, 0))   # packed first, so it sits on
    bigger_btn.pack(side="right")                  # the right of the pair

    root.bind("<Return>", go_next)
    root.bind("<KP_Enter>", go_next)   # the keypad Enter is the one a lot of
                                       # people actually press, and it did nothing

    # Resume exactly where they stopped. A finished setup starts from the top
    # instead, so re-opening it is a review rather than a confusing "Finish".
    if not state.get("completed"):
        while idx[0] < len(qs[0]) - 1 and qs[0][idx[0]]["key"] in state:
            idx[0] += 1
    apply_zoom()
    draw()
    root.update_idletasks()
    root.geometry("+%d+%d" % (max(0, (root.winfo_screenwidth() - seen[0]) // 2),
                              max(0, (root.winfo_screenheight() - seen[1]) // 3)))
    root.mainloop()
    return 0


_REHEARSAL = []


def _rehearse_window(root, cfg_path, f_body, f_q, f_btn=None):
    """Show the script in the same window family. Never opens a terminal."""
    import tkinter as tk
    f_btn = f_btn or f_body

    if _REHEARSAL and _REHEARSAL[0].winfo_exists():
        _REHEARSAL[0].deiconify()
        _REHEARSAL[0].lift()
        return _REHEARSAL[0]

    top = tk.Toplevel(root)
    _REHEARSAL[:] = [top]
    top.title("Practice call")
    top.configure(bg=BG)
    top.transient(root)          # otherwise it hides behind the setup window
    frame = tk.Frame(top, bg=BG, padx=40, pady=32)
    frame.pack(fill="both", expand=True)
    try:
        from cura.setup.preview import preview_lines
        lines = preview_lines(str(cfg_path))
    except Exception as e:
        lines = [("error", f"Couldn't build the practice call: {e}")]

    tk.Label(frame, text="This is what they will hear.", font=f_q, bg=BG,
             fg=FG, anchor="w", justify="left").pack(fill="x", pady=(0, 18))

    buttons = tk.Frame(frame, bg=BG)
    buttons.pack(side="bottom", fill="x", pady=(24, 0))

    body = tk.Frame(frame, bg=BG)
    body.pack(fill="both", expand=True)
    bar = tk.Scrollbar(body, width=26)     # more than half the script used to be
    bar.pack(side="right", fill="y")       # below the fold with nothing to say so
    box = tk.Text(body, font=f_body, bg="#F7F7F7", fg=FG, relief="flat",
                  wrap="word", padx=18, pady=18, height=12, width=42,
                  highlightthickness=3, highlightbackground=EDGE,
                  highlightcolor=ACCENT, yscrollcommand=bar.set, takefocus=True)
    box.pack(side="left", fill="both", expand=True)
    bar.config(command=box.yview)

    for kind, text in lines:
        box.insert("end", ("\n" + text + "\n\n") if kind == "heading" else ("   " + text + "\n"))
    box.config(state="disabled")

    # A disabled Text ignores the arrow keys, so give it its own.
    def scroll(amount):
        def go(_e=None):
            box.yview_scroll(amount, "units")
            return "break"
        return go
    box.bind("<Up>", scroll(-2))
    box.bind("<Down>", scroll(2))
    box.bind("<Prior>", scroll(-10))
    box.bind("<Next>", scroll(10))
    box.bind("<Home>", lambda e: (box.yview_moveto(0), "break")[1])
    box.bind("<End>", lambda e: (box.yview_moveto(1), "break")[1])

    def close():
        _REHEARSAL.clear()
        top.destroy()

    btn = _button(tk, buttons, "Close", close, f_btn, primary=True)
    btn.pack(side="right")
    top.protocol("WM_DELETE_WINDOW", close)
    top.bind("<Escape>", lambda e: close())

    top.update_idletasks()
    # Capped, not just clamped to the screen: a 1300px line of 20pt text is a
    # line you lose your place in halfway across.
    w = min(max(760, top.winfo_reqwidth()), 980, max(400, top.winfo_screenwidth() - 80))
    h = min(max(520, top.winfo_reqheight()), max(300, top.winfo_screenheight() - 140))
    top.geometry(f"{w}x{h}")
    top.minsize(min(640, w), min(420, h))
    box.focus_set()
    return top


if __name__ == "__main__":
    sys.exit(run())
