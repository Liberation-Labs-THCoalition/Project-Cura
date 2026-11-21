"""Console — talk to Cura from your terminal.

For caregivers testing the setup, or for elders comfortable with
a computer or tablet. Same warmth, same care, no phone needed.

Usage:
  python -m cura.console --name Margaret
  python -m cura.console --name Margaret --demo

Demo mode runs a simulated morning check-in to show what calls
sound like. Interactive mode is a free conversation.
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timezone
from typing import Any

from cura.pulse.eldercare_pulse import ElderProfile, EldercarePulseConfig
from cura.pulse.checkin_composer import CheckinComposer
from cura.pulse.daily_enrichments import CognitiveExercise
from cura.privacy.scam_shield import ScamShield
from cura.sensors.wearable import WearableAnalyzer


#: What the console says when someone may be in trouble. The console has no way
#: to reach anyone, so it says so, and names who can help.
CANNOT_REACH_ANYONE = (
    "I can't reach your family from here. This chat doesn't contact anyone. "
    "If you need help now, please call 911, or call someone you trust. "
    "I'll stay right here with you."
)


def _timestamp() -> str:
    return datetime.now().strftime("%I:%M %p")


def _cura_says(text: str) -> None:
    print(f"\n  Cura: {text}")


def _elder_input(name: str) -> str:
    try:
        return input(f"\n  {name}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def run_demo(config: EldercarePulseConfig, weather: dict | None = None) -> None:
    """Run a simulated morning check-in."""
    composer = CheckinComposer()
    # keypad=False: nothing in the console can hear a key or call anyone, and
    # this profile has no phone and no contacts. The demo printed "If you ever
    # need help, press two and I'll call your family" for it (batch 11
    # verifier, MEDIUM). What the phone says instead is told below, as
    # narration, not in Cura's voice.
    checkin = composer.compose_morning(config, weather=weather, keypad=False)
    name = config.profile.display_name

    print("\n" + "=" * 60)
    print(f"  DEMO: Morning Check-in for {name}")
    print(f"  Time: {_timestamp()}")
    print("=" * 60)

    print("\n  [Ring... ring... ring...]")
    print(f"  [{name} picks up the phone]")

    for msg in checkin.all_messages:
        _cura_says(msg)

    print(f"\n  [{name} presses 1 — medications confirmed]")
    _cura_says("Thank you. I'm glad you're staying on top of your medications. "
               "Have a wonderful day.")

    print("\n" + "=" * 60)
    print("  That's what a morning check-in sounds like.")
    print("  Cura calls twice a day, warm and consistent.")
    print("  On a real call the last line is different: it tells her to press")
    print("  two for her family. Cura only places real calls once setup has")
    print("  someone it can reach. This demo calls nobody.")
    print("=" * 60 + "\n")


def run_interactive(config: EldercarePulseConfig) -> None:
    """Interactive conversation with Cura."""
    name = config.profile.display_name
    scam_shield = ScamShield()
    cognitive = CognitiveExercise()

    print("\n" + "=" * 60)
    print(f"  Cura — talking with {name}")
    print("  Type 'quit' or 'bye' to end the conversation.")
    print("  Type 'help' for options.")
    print("=" * 60)

    _cura_says(f"Hello, {name}. I'm glad you're here. What's on your mind?")

    while True:
        response = _elder_input(name)
        if not response:
            continue

        lower = response.lower()

        if lower in ("quit", "bye", "goodbye", "exit"):
            _cura_says(f"It was lovely talking to you, {name}. "
                       "I'm always here when you need me. Take care.")
            break

        if lower == "help":
            _cura_says("You can talk to me about anything. Here are some things I can help with:")
            print("    - Ask about your medications")
            print("    - Tell me about a suspicious call or email")
            print("    - Ask me to read to you")
            print("    - Play a word game")
            print("    - Just chat")
            continue

        # Distress before scam words, as the phone path does: "I fell and I'm
        # in trouble" ("in trouble" is a scam keyword) got the scam reply,
        # which never mentions 911 (batch 11 verifier, MEDIUM).
        # Check for distress
        if any(w in lower for w in ["help", "emergency", "hurt", "fall", "fell", "pain", "scared"]):
            # The console contacts nobody: no phone line, no contacts, no
            # escalation callback. It used to say "I'm alerting your family
            # right now. Stay calm, stay where you are." Nothing was sent, and
            # "stay where you are" told a person who had fallen to wait for help
            # that was not coming. Say what is true, and who can help.
            _cura_says(f"{name}, I hear you. {CANNOT_REACH_ANYONE}")
            continue

        # Check for scam indicators
        alert = scam_shield.analyze_response(response)
        if alert:
            # The alert stays in this process and is gone when the chat ends;
            # nobody is told. This used to add "I'm flagging this for your
            # family right away" on top of a reassurance that said the same.
            _cura_says(scam_shield.get_reassurance(family_told=False))
            if alert.severity >= 0.8:
                _cura_says("This one worries me, so please tell them today if "
                           "you can. You did absolutely the right thing telling me.")
            continue

        # Medication questions
        if any(w in lower for w in ["medication", "medicine", "pill", "pills", "prescription"]):
            meds = config.profile.medications
            if meds:
                med_list = ", ".join(m.get("name", "medication") for m in meds)
                _cura_says(f"Your current medications are: {med_list}. "
                           "Would you like to know when to take them?")
            else:
                _cura_says("I don't have your medication list yet. "
                           "Ask your caregiver to add them to your profile.")
            continue

        # Games
        if any(w in lower for w in ["game", "play", "puzzle", "fun"]):
            enrichment = cognitive.word_game()
            _cura_says(enrichment.message)
            continue

        # Reading
        if any(w in lower for w in ["read", "book", "story", "poem"]):
            _cura_says("I'd love to read to you. Ask your caregiver to load a book, "
                       "and I'll read a chapter during our next call. "
                       "Do you have a favorite book you'd like me to read?")
            continue

        # Weather
        if any(w in lower for w in ["weather", "temperature", "cold", "hot", "rain", "snow"]):
            _cura_says("I can check the weather for you during our regular calls. "
                       "If it's going to be very hot or cold, I'll always let you know.")
            continue

        # Loneliness / feelings
        if any(w in lower for w in ["lonely", "alone", "miss", "sad", "bored"]):
            _cura_says(f"I'm sorry you're feeling that way, {name}. "
                       "I'm here with you right now, and I enjoy our talks. "
                       "Would you like to play a word game, or just keep chatting?")
            continue

        # General conversation
        responses = [
            f"Thank you for sharing that, {name}. Tell me more.",
            f"That's interesting. What else is on your mind?",
            f"I hear you, {name}. I'm glad you told me.",
            f"That's wonderful. I enjoy hearing about your day.",
            f"How does that make you feel, {name}?",
        ]
        _cura_says(random.choice(responses))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Cura Console — talk to Cura from your terminal",
    )
    parser.add_argument("--name", type=str, default="friend",
                        help="Elder's preferred name")
    parser.add_argument("--demo", action="store_true",
                        help="Run a demo morning check-in")
    parser.add_argument("--medications", type=str, nargs="*", default=[],
                        help="Medication names (for demo)")
    args = parser.parse_args()

    from cura.pulse.medication import split_medication
    # Never fabricate a timing. An invented "morning" is announced as fact.
    medications = [split_medication(m) for m in args.medications]

    profile = ElderProfile(
        name=args.name,
        preferred_name=args.name,
        phone="",
        medications=medications,
        emergency_contacts=[],
        primary_caregiver={},
    )
    config = EldercarePulseConfig(profile)

    if args.demo:
        run_demo(config, weather={"temp_f": 88})
    else:
        run_interactive(config)


if __name__ == "__main__":
    main()
