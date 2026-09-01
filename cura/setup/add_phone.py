"""Turn on real phone calls.

Deliberately separate from `cura setup`. Phone service needs an account with an
outside company, and making someone do that in the middle of setup is what breaks
momentum — you hit a signup form, get interrupted, and never come back.

By the time anyone runs this they have already heard a rehearsal and know exactly
what they are switching on. That is what makes the signup worth doing.

Same rules as the wizard: one question at a time, saved the instant it is answered,
resumable after any interruption, no JSON, no jargon.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from cura.setup.wizard import say, rule, load, save, ask, STATE

TWILIO_CONSOLE = "https://console.twilio.com"


def a_sid(v: str) -> str | None:
    if re.fullmatch(r"AC[0-9a-fA-F]{32}", v.strip()):
        return None
    return ("That doesn't look right. The Account SID starts with the letters AC "
            "and is quite long. Copy the whole thing.")


def a_token(v: str) -> str | None:
    if re.fullmatch(r"[0-9a-fA-F]{32}", v.strip()):
        return None
    return ("That doesn't look right. The Auth Token is a long string of letters "
            "and numbers, with no spaces.")


def a_phone(v: str) -> str | None:
    if len(re.sub(r"\D", "", v)) >= 10:
        return None
    return "That doesn't look like a full phone number."


def run() -> int:
    state = load()
    if not state.get("completed"):
        print()
        say("Let's finish the main setup first — it only takes a few minutes.")
        say("Run this:", blank_after=1)
        print("      cura setup\n")
        return 1

    who = state.get("preferred_name", "your loved one")

    print("\n")
    say("TURNING ON PHONE CALLS", blank_after=1)
    say(f"Right now Cura can rehearse, but it can't actually dial {who}.")
    say("To place real calls it needs a phone line of its own, from a company")
    say("called Twilio. It costs about a dollar a month plus a penny or two")
    say("per minute.")
    say("")
    say("This takes about ten minutes, and you only do it once.")
    say("")
    say("As always: stop whenever you need to. Everything is saved as you go.")

    if "twilio_sid" not in state:
        rule()
        say("STEP 1 — Make the account", blank_after=1)
        say(f"In your web browser, go to:", blank_after=1)
        print(f"      {TWILIO_CONSOLE}\n")
        say("Sign up with your email. When it asks what you're building, any")
        say("answer is fine — it doesn't change anything.")
        say("")
        say("They will give you free trial credit, which is plenty to test with.")
        say("")
        try:
            input("  Press Enter once you're signed in and looking at the console. > ")
        except (EOFError, KeyboardInterrupt):
            print(); say("Stopped. Run 'cura add-phone' again whenever you're ready.")
            return 0

    ask(state, "twilio_sid",
        "STEP 2 — On that page, find 'Account SID' and copy it here.",
        "It's on the main console page, usually under 'Account Info'. "
        "It starts with AC. You can paste it.",
        validate=a_sid)

    ask(state, "twilio_token",
        "STEP 3 — Just below it, find 'Auth Token' and copy that here.",
        "You may have to click 'Show' or an eye icon to reveal it first. "
        "Nobody else ever sees this — it stays on your computer.",
        validate=a_token)

    if "twilio_number" not in state:
        rule()
        say("STEP 4 — Get Cura its own phone number", blank_after=1)
        say("In the Twilio menu, choose Phone Numbers, then 'Buy a number'.")
        say("Pick any number with Voice capability — a local area code is nice")
        say(f"so it looks familiar to {who}, but any number works.")
        say("")

    ask(state, "twilio_number",
        "STEP 5 — What is the number you just got?",
        "Copy it exactly as Twilio shows it.",
        validate=a_phone)

    # ---- write credentials into the config -------------------------------
    cfg_path = Path(state.get("config_path", ""))
    if not cfg_path.exists():
        say("Hmm — I can't find the setup file. Try running 'cura setup' again;")
        say("it will pick up everything you've already answered.")
        return 1

    digits = re.sub(r"\D", "", state["twilio_number"])
    if len(digits) == 10:
        digits = "1" + digits

    cfg = json.loads(cfg_path.read_text())
    cfg["twilio"] = {
        "account_sid": state["twilio_sid"].strip(),
        "auth_token": state["twilio_token"].strip(),
        "phone_number": "+" + digits,
    }
    tmp = cfg_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2))
    os.replace(tmp, cfg_path)
    try:
        cfg_path.chmod(0o600)  # the auth token lives here now
    except OSError:
        pass

    state["phone_enabled"] = True
    save(state)

    rule()
    say("Phone calls are on.", blank_after=1)
    say(f"Cura will call {who} in the morning and again in the evening.")
    say("")
    say("To start it running:", blank_after=1)
    print("      cura run --config " + str(cfg_path) + "\n")
    say("You can still hear a practice call any time with:", blank_after=1)
    print("      cura rehearse\n")
    rule()
    return 0


if __name__ == "__main__":
    sys.exit(run())
