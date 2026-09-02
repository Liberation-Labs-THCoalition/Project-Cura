"""Cura setup wizard — builds the config by asking, never by editing JSON.

Design constraints, taken from a real caregiver who gave up partway through the
manual setup:

  - He is caring for someone with late-stage dementia. He gets SMALL, UNPREDICTABLE
    windows and will be interrupted mid-setup. Interruption is the normal case, not
    the edge case. So: every answer is saved the moment it is given, and re-running
    resumes exactly where he stopped. Nothing is ever asked twice.
  - His eyesight is failing. Large plain text, generous spacing, no colour-only
    signals, no dense blocks, no small status lines.
  - He is tech-forward but not a programmer. He should never see JSON, a stack
    trace, or the word "config".
  - Every question is a place to lose him. So there are as few as possible, each
    one is a single thing, and anything that can wait until later does.

Twilio is deliberately NOT asked here. Phone calling needs an external signup, and
hitting that mid-setup is what breaks momentum. Finish setup, watch a rehearsal
call print to the screen, THEN add phone service as a separate, clearly optional
step. Seeing it work first is what makes the second step worth doing.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

STATE = Path.home() / ".cura" / "setup-progress.json"
OUT_DIR = Path.home() / ".cura"

W = 64  # wrap width — wide enough to avoid ragged text, narrow enough to scan


def say(text: str = "", blank_after: int = 1) -> None:
    """Print wrapped, generously spaced text."""
    import textwrap
    if text:
        for para in text.split("\n"):
            if not para.strip():
                print()
                continue
            for line in textwrap.wrap(para, W) or [""]:
                print("  " + line)
    print("\n" * blank_after, end="")


def rule() -> None:
    print("\n  " + "─" * W + "\n")


def load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def save(state: dict) -> None:
    """Persist progress atomically, and never world-readable.

    This file accumulates the Twilio auth token (add-phone writes it here),
    both phone numbers, the medication list and the address. It was being
    written at mode 664 -- readable by anyone with an account on the machine --
    while add_phone carefully chmodded the *config* to 600. The secret was
    protected in one of the two places it lands.

    Directory and file are both narrowed, and the mode is set on the temp file
    BEFORE the rename, so there is no window where the token exists at the
    final path with the wrong permissions.
    """
    STATE.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(STATE.parent, 0o700)
    except OSError:
        pass
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, STATE)  # atomic: an interruption never leaves a half-written file


def ask(state: dict, key: str, question: str, help_text: str = "",
        validate=None, default: str | None = None, optional: bool = False) -> str:
    """Ask once, save immediately, never ask again.

    Saving before returning is the whole point: if the phone rings between this
    question and the next, nothing is lost and nothing is repeated.
    """
    if key in state:
        return state[key]

    while True:
        rule()
        say(question, blank_after=1)
        if help_text:
            say(help_text, blank_after=1)
        if optional:
            say("(You can press Enter to skip this and add it later.)", blank_after=1)
        elif default:
            say(f"(Press Enter to use: {default})", blank_after=1)

        try:
            raw = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            say("Stopped. Nothing is lost — run the same command again and it will")
            say("pick up right here.")
            sys.exit(0)

        if not raw and default is not None:
            raw = default
        if not raw and optional:
            state[key] = ""
            save(state)
            return ""
        if not raw:
            say("This one is needed. Please type an answer.")
            continue
        if validate:
            problem = validate(raw)
            if problem:
                say(problem)
                continue

        state[key] = raw
        save(state)
        return raw


# ---------------------------------------------------------------- validators

def a_phone(v: str) -> str | None:
    digits = re.sub(r"\D", "", v)
    if len(digits) == 10 or (len(digits) == 11 and digits.startswith("1")):
        return None
    return ("That doesn't look like a 10-digit phone number. "
            "You can write it any way you like — 555-123-4567 is fine.")


def norm_phone(v: str) -> str:
    d = re.sub(r"\D", "", v)
    if len(d) == 10:
        d = "1" + d
    return "+" + d


def an_hour(v: str) -> str | None:
    m = re.match(r"^(\d{1,2})\s*(am|pm)?$", v.strip(), re.I)
    if not m:
        return "Please give a time like 8am or 7pm."
    h = int(m.group(1))
    if not 1 <= h <= 12 and not 0 <= h <= 23:
        return "Please give an hour between 1 and 12, like 8am."
    return None


def to_hour24(v: str) -> int:
    m = re.match(r"^(\d{1,2})\s*(am|pm)?$", v.strip(), re.I)
    h, mer = int(m.group(1)), (m.group(2) or "").lower()
    if mer == "pm" and h != 12:
        h += 12
    if mer == "am" and h == 12:
        h = 0
    return h


# ---------------------------------------------------------------- the wizard

def run() -> int:
    state = load()
    resuming = bool(state)

    print("\n")
    say("CURA SETUP", blank_after=1)

    if resuming:
        say("Welcome back. Picking up where you left off — you won't be asked")
        say("anything you've already answered.")
    else:
        say("This asks a few simple questions and sets everything up for you.")
        say("It takes about five minutes.")
        say("")
        say("You can stop at any time. Every answer is saved the moment you give")
        say("it, so if you get interrupted, just run this again and it continues")
        say("from where you stopped. Nothing is ever lost.")

    name = ask(state, "name",
               "What is the name of the person Cura will be calling?",
               "First and last name is fine.")
    first = name.split()[0]

    ask(state, "preferred_name",
        f"What does {first} like to be called?",
        "This is what Cura will say on the phone.",
        default=first)

    ask(state, "phone",
        f"What phone number should Cura call to reach {first}?",
        "A landline is perfectly fine. Any format works.",
        validate=a_phone)

    ask(state, "morning",
        f"About what time does {first} usually start the day?",
        "Cura will make a friendly morning check-in around then. "
        "Something like 8am.",
        validate=an_hour, default="8am")

    ask(state, "evening",
        f"And about what time does {first} settle in for the evening?",
        "Cura will check in again then. Something like 7pm.",
        validate=an_hour, default="7pm")

    ask(state, "caregiver_name",
        "What is your name?",
        "If Cura is ever concerned about something, this is who it tells.")

    ask(state, "caregiver_phone",
        "And the best phone number to reach you?",
        "Cura will call or text you if something seems wrong.",
        validate=a_phone)

    ask(state, "meds",
        f"Does {first} take any regular medications?",
        "Just list them separated by commas — for example: "
        "Lisinopril, Metformin. Cura will offer gentle reminders. "
        "Don't worry about doses or exact spelling.",
        optional=True)

    ask(state, "address",
        f"What is {first}'s address?",
        "Only used if emergency services ever need to be told where to go.",
        optional=True)

    # ---- build the real config -------------------------------------------
    meds = [m.strip() for m in (state.get("meds") or "").split(",") if m.strip()]
    cfg = {
        "name": state["name"],
        "preferred_name": state["preferred_name"],
        "phone": norm_phone(state["phone"]),
        "medications": [{"name": m, "time": "morning"} for m in meds],
        "emergency_contacts": [{
            "name": state["caregiver_name"],
            "phone": norm_phone(state["caregiver_phone"]),
            "relation": "caregiver",
        }],
        "primary_caregiver": {
            "name": state["caregiver_name"],
            "phone": norm_phone(state["caregiver_phone"]),
        },
        "morning_time": to_hour24(state["morning"]),
        "evening_time": to_hour24(state["evening"]),
    }
    if state.get("address"):
        cfg["address"] = state["address"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-z0-9]+", "-", state["preferred_name"].lower()).strip("-") or "person"
    out = OUT_DIR / f"{safe}.json"
    out.write_text(json.dumps(cfg, indent=2))
    try:
        out.chmod(0o600)  # address, numbers, medication list
    except OSError:
        pass

    rule()
    say("All set. Cura is ready.", blank_after=1)
    say(f"Everything is saved for {state['preferred_name']}.")
    say("")
    say("Next: let's watch a practice call, so you can see exactly what")
    say(f"{state['preferred_name']} will hear. Nothing is dialled — it just")
    say("prints to the screen.")
    say("")
    say("Run this:", blank_after=1)
    print(f"      cura rehearse\n")
    say("When you're ready to switch on real phone calls, run:", blank_after=1)
    print("      cura add-phone\n")
    say("There is no rush. Cura works for practice runs without it.")
    rule()

    state["completed"] = True
    state["config_path"] = str(out)
    save(state)
    return 0


if __name__ == "__main__":
    sys.exit(run())
