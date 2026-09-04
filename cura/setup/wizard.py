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
    """Normalise to E.164, or return "" when there is no number here.

    Returned "+" for empty input — a string that is truthy, non-empty after
    strip, and therefore passed escalation_readiness's "has a phone number"
    test while being unable to receive a call. A blank answer became an
    emergency contact Cura believed it could reach.
    """
    d = re.sub(r"\D", "", v or "")
    if len(d) == 10:
        d = "1" + d
    if len(d) != 11 or not d.startswith("1") or d[1] in "01":
        # A country code cannot begin with 0, and a NANP area code cannot begin
        # with 0 or 1. Twilio rejects these outright, so accepting them here
        # only moves the failure to the moment help is needed.
        return ""
    return "+" + d



def a_yes_no(v: str) -> str | None:
    if _is_yes(v) is None:
        return "Please answer yes or no."
    return None


def _is_yes(v: str) -> bool | None:
    s = (v or "").strip().lower()
    if s in ("y", "yes", "yeah", "yep", "she can", "he can", "they can", "sometimes"):
        return True
    if s in ("n", "no", "nope", "not really", "she can't", "he can't",
             "she cannot", "he cannot", "not any more", "not anymore"):
        return False
    return None


def an_hour(v: str) -> str | None:
    """Validate a check-in hour.

    The old test was `not 1 <= h <= 12 and not 0 <= h <= 23`, which reduces to
    `not 0 <= h <= 23` — so 13 through 23 passed a check whose message says
    "between 1 and 12". "13pm" then became hour 25, and `cura run` died with an
    unhandled ValueError when it tried to schedule it. The phone never rang,
    and setup had said "All set."
    """
    m = re.match(r"^(\d{1,2})\s*(am|pm)?$", (v or "").strip(), re.I)
    if not m:
        return "Please give a time like 8am or 7pm."
    h, mer = int(m.group(1)), (m.group(2) or "").lower()
    if mer and not 1 <= h <= 12:
        return f"There's no such time as {h}{mer}. Please give an hour like 8am or 7pm."
    if not mer and not 0 <= h <= 23:
        return "Please give an hour between 0 and 23, or a time like 8am."
    return None


def to_hour24(v: str, default: int | None = None) -> int:
    """Parse to a 24-hour hour, never returning one that cannot exist.

    Previously `m.group(1)` on a failed match raised AttributeError inside
    finish(), so clearing a pre-filled time field in the setup window bricked
    setup permanently with a stack trace. And "13pm" produced 25, which no
    scheduler accepts.
    """
    m = re.match(r"^(\d{1,2})\s*(am|pm)?$", (v or "").strip(), re.I)
    if m:
        h, mer = int(m.group(1)), (m.group(2) or "").lower()
        if mer == "pm" and h != 12:
            h += 12
        if mer == "am" and h == 12:
            h = 0
        if 0 <= h <= 23:
            return h
    if default is not None:
        return default
    raise ValueError(f"{v!r} is not a time of day Cura can use")





def _household_block(state: dict, meds: list, cfg: dict) -> dict:
    """Turn the answers into members, roles and permission to call.

    The load-bearing answer is `can_answer`. If the person being cared for
    cannot answer a phone -- which is the first household's actual situation --
    they are recorded reach=never and get NO check-ins, and the caregiver gets
    them instead. That is not a degraded mode; it is the arrangement.
    """
    # _safe_stem handles non-Latin names via a stable digest, so a member_id
    # exists for every person rather than only the Latin-alphabet ones.
    from cura.memory.companion_memory import _safe_stem as _slug

    elder_id = _slug(state.get("preferred_name") or state.get("name", "elder"))
    care_id = _slug(state.get("caregiver_name") or "caregiver")
    if care_id == elder_id:
        care_id = care_id + "-caregiver"

    can_answer = _is_yes(state.get("can_answer", "")) is True
    morning = cfg["morning_time"]
    evening = cfg["evening_time"]

    elder = {
        "member_id": elder_id,
        "name": state["name"],
        "preferred_name": state.get("preferred_name", ""),
        "phone": cfg["phone"],
        "reach": "scheduled" if can_answer else "never",
        "medications": meds,
        "address": cfg.get("address", ""),
        "checkins": ([{"slot": "morning", "about": [elder_id]},
                      {"slot": "evening", "about": [elder_id]}]
                     if can_answer else []),
    }
    caregiver = {
        "member_id": care_id,
        "name": state.get("caregiver_name", ""),
        "preferred_name": state.get("caregiver_name", "").split(" ")[0],
        "phone": norm_phone(state.get("caregiver_phone", "")),
        "reach": "scheduled" if not can_answer else "on_request",
        "cares_for": [elder_id],
        "address": cfg.get("address", ""),
        # When she cannot be called, HE gets the check-in, and it is about both
        # of them -- he is being asked after as well as asked about her.
        "checkins": ([{"slot": "evening", "about": [elder_id, care_id]}]
                     if not can_answer else []),
    }
    return {"members": [elder, caregiver],
            "subject": elder_id,
            "morning_hour": morning, "evening_hour": evening}


def write_config(out: Path, cfg: dict) -> None:
    """Write the config WITHOUT destroying what setup did not author.

    `add_phone` writes the Twilio block into this same file. Both wizards
    rebuilt cfg from scratch and wrote over the top of it, so re-running setup
    silently deleted the credentials — and nothing noticed: state["phone_enabled"]
    stayed True and the closing screen still said "All set. Cura is ready."
    install.sh re-runs setup, so this was reachable by following our own
    instructions.
    """
    existing = {}
    if out.exists():
        raw = ""
        try:
            raw = out.read_text()
            existing = json.loads(raw)
        except OSError as e:
            raise RuntimeError(
                f"cannot read {out} to merge into it: {e}") from e
        except ValueError as e:
            # A config we cannot PARSE is not an empty config. Treating it as
            # one made the merge discard everything -- including the Twilio auth
            # token -- which is the exact loss this function exists to prevent,
            # reachable through a file that is merely corrupt. Silent, too: no
            # error, no backup, the credentials simply gone.
            #
            # Found by a question from Nexus, who asked whether the merge
            # preserves comments. It does not, because the format is strict
            # JSON -- but a commented config is unparseable, and unparseable was
            # being read as empty.
            salvage = out.with_suffix(".unreadable")
            try:
                salvage.write_text(raw)
                salvage.chmod(0o600)
            except OSError:
                salvage = None
            raise RuntimeError(
                f"{out} exists but is not valid JSON ({e}). Refusing to write "
                f"over it, because merging into an unreadable file would delete "
                f"whatever it holds — including phone credentials."
                + (f" A copy is at {salvage}." if salvage else "")) from e
    if not isinstance(existing, dict):
        raise RuntimeError(
            f"{out} holds {type(existing).__name__}, not an object; refusing to "
            f"merge into it")
    merged = {**existing, **cfg}
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(merged, indent=2))
    try:
        tmp.chmod(0o600)      # before the rename: no window at the final path
    except OSError:
        pass
    os.replace(tmp, out)


def readiness_problems(cfg: dict) -> list[str]:
    """What still stops Cura summoning help, in plain words.

    Both wizards printed "Cura is ready" as an unconditional string. It is a
    claim about the config, so it has to be checked against the config —
    otherwise it is a check that cannot fail.
    """
    from cura.pulse.eldercare_pulse import ElderProfile
    from cura.comms.escalation import escalation_readiness
    return escalation_readiness(ElderProfile(
        name=cfg.get("name", ""),
        preferred_name=cfg.get("preferred_name", ""),
        phone=cfg.get("phone", ""),
        medications=cfg.get("medications", []),
        emergency_contacts=cfg.get("emergency_contacts", []),
        primary_caregiver=cfg.get("primary_caregiver", {}),
    ))


# ---------------------------------------------------------------- the wizard

def _meds_with_timings(state: dict, first: str, ask) -> list[dict]:
    """Medications with the timing the caregiver actually gave, asking about
    any that are still unclear.

    The wizard used to store each entry whole as the drug NAME and fabricate
    "morning" as the time. So "oxycodone as needed for pain" became a daily
    8am announcement of a rescue opioid, "Alendronate on Sundays" was announced
    seven days a week, and -- worst of the three -- both caregiver-warning
    lists reported ALL CLEAR, because a fabricated timing does not look
    unknown. A check that cannot fail is indistinguishable from a check that
    passed.

    Nothing here invents a timing. An entry Cura cannot place stays empty,
    which routes to Schedule.UNKNOWN: silence, and a question.
    """
    from cura.pulse.medication import (parse_medication_list, parse_medication,
                                       Schedule)
    meds = parse_medication_list(state.get("meds") or "")
    for i, med in enumerate(meds):
        if parse_medication(med).schedule is not Schedule.UNKNOWN:
            continue
        answer = ask(state, f"med_time_{i}",
                     f"When does {first} take {med['name']}?",
                     "For example: in the morning, at bedtime, twice daily, "
                     "on Sundays, or as needed for pain. "
                     "If you're not sure, press Enter — Cura will stay quiet "
                     "about this one rather than guess at the wrong time.",
                     optional=True)
        if answer.strip():
            med["time"] = answer.strip()
            state[f"med_time_{i}"] = answer.strip()
    return meds


def clear_answers() -> None:
    """Forget the saved answers so the questions can be asked again.

    ask() returns early for any key already in state, so once setup completed
    it asked NOTHING on every later run: a wrong phone number could not be
    corrected, and there was no way to set Cura up for a different person. The
    config file itself is left alone, so the Twilio block and anything else
    setup did not author survive.
    """
    try:
        STATE.unlink()
    except FileNotFoundError:
        pass


def run(again: bool = False) -> int:
    if again:
        clear_answers()
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

    ask(state, "can_answer",
        f"Can {first} answer a phone and have a conversation?",
        "It's completely fine if not — many of the people Cura looks after "
        "can't, and Cura works differently for them. If the answer is no, "
        "Cura won't ring their phone at all; it will call you instead and "
        "keep track of things for you.",
        validate=a_yes_no)

    ask(state, "meds",
        f"Does {first} take any regular medications?",
        "List them separated by commas, and say when each one is taken — "
        "for example: Lisinopril in the morning, Metformin twice daily, "
        "Alendronate on Sundays, oxycodone as needed for pain. "
        "Don't worry about doses or exact spelling. "
        "If you're not sure about one, just name it and Cura will ask.",
        optional=True)

    _meds_with_timings(state, first, ask)

    ask(state, "address",
        f"What is {first}'s address?",
        "Only used if emergency services ever need to be told where to go.",
        optional=True)

    # ---- build the real config -------------------------------------------
    # The timing he wrote is kept. Previously every entry was stored whole as
    # the NAME with "morning" fabricated as the time, so "oxycodone as needed
    # for pain" became a daily 8am announcement of a rescue opioid, and both
    # caregiver-warning lists reported all clear because nothing looked unknown.
    meds = _meds_with_timings(state, first, ask)
    cfg = {
        "name": state["name"],
        "preferred_name": state["preferred_name"],
        "phone": norm_phone(state["phone"]),
        "medications": meds,
        "emergency_contacts": [{
            "name": state["caregiver_name"],
            "phone": norm_phone(state["caregiver_phone"]),
            "relation": "caregiver",
        }],
        "primary_caregiver": {
            "name": state["caregiver_name"],
            "phone": norm_phone(state["caregiver_phone"]),
        },
        "morning_time": to_hour24(state.get("morning", ""), default=8),
        "evening_time": to_hour24(state.get("evening", ""), default=20),
    }
    # The household block. cura/household/ existed with ZERO production call
    # sites -- nothing anywhere constructed a Household, so the model written to
    # fix unjoined halves was itself one. This is the join.
    cfg["household"] = _household_block(state, meds, cfg)
    if state.get("address"):
        cfg["address"] = state["address"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-z0-9]+", "-", state["preferred_name"].lower()).strip("-") or "person"
    out = OUT_DIR / f"{safe}.json"
    write_config(out, cfg)

    rule()
    problems = readiness_problems(cfg)
    if problems:
        # "Cura is ready" is a claim about the config, so it gets checked
        # against the config. Saying it unconditionally is a check that cannot
        # fail, and the thing it would have failed on is whether anyone can be
        # reached when she needs help.
        say("Almost there — but not ready yet.", blank_after=1)
        say(f"Everything is saved for {state['preferred_name']}, and Cura will")
        say("not start until this is sorted:")
        say("")
        for prob in problems:
            say(f"  - {prob}")
        say("")
        say("Run this again to fix it:")
        say("")
        say("      cura setup --again")
        say("")
        return
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
