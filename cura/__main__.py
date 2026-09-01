"""Cura — start here.

Usage:
  python -m cura console --name Margaret                    # Chat in terminal
  python -m cura console --name Margaret --demo             # See a demo check-in
  python -m cura run --config my_elder.json                 # Start daily calls
  python -m cura webhook --port 5000 --elder-name Margaret  # Start webhook server

The console is for testing and conversation.
The runner starts the daily check-in schedule.
The webhook handles Margaret's responses during calls.
"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cura",
        description="Cura — a faithful companion for aging at home",
    )
    subparsers = parser.add_subparsers(dest="command", help="What to do")

    # Console
    console_parser = subparsers.add_parser(
        "console", help="Talk to Cura in your terminal",
    )
    console_parser.add_argument("--name", type=str, default="friend",
                                help="Elder's preferred name")
    console_parser.add_argument("--demo", action="store_true",
                                help="Run a demo morning check-in")
    console_parser.add_argument("--medications", type=str, nargs="*", default=[],
                                help="Medication names")

    # Webhook server
    webhook_parser = subparsers.add_parser(
        "webhook", help="Start the Twilio webhook server",
    )
    webhook_parser.add_argument("--port", type=int, default=5000)
    webhook_parser.add_argument("--elder-name", type=str, default="friend")

    # Run (scheduled calls)
    run_parser = subparsers.add_parser(
        "run", help="Start scheduled daily check-ins",
    )
    run_parser.add_argument("--config", type=str, required=True,
                            help="Path to elder config JSON file")
    run_parser.add_argument("--dry-run", action="store_true",
                            help="Log calls without actually dialing")

    # Setup, rehearsal, and phone-service commands. These exist because the
    # wizard's closing screen names them; a setup flow that ends by telling
    # someone to run a command that does not exist is worse than no wizard.
    setup_parser = subparsers.add_parser(
        "setup", help="Set up Cura by answering a few questions")
    setup_parser.add_argument("--window", action="store_true",
                              help="Open a window instead of using the terminal")

    rehearse_parser = subparsers.add_parser(
        "rehearse", help="Hear what a check-in will sound like. Nothing is dialled.")
    rehearse_parser.add_argument("--config", type=str, default=None,
                                 help="Defaults to the one setup created")

    subparsers.add_parser(
        "add-phone", help="Turn on real phone calls (needs a Twilio account)")

    args = parser.parse_args()

    if args.command == "setup":
        if getattr(args, "window", False):
            from cura.setup.gui import run as gui_run
            sys.exit(gui_run())
        from cura.setup.wizard import run as setup_run
        sys.exit(setup_run())

    if args.command == "rehearse":
        cfg = args.config or _default_config_path()
        if not cfg:
            print("\n  Cura isn't set up yet. Run this first:\n")
            print("      cura setup\n")
            sys.exit(1)
        _preview(cfg)
        sys.exit(0)

    if args.command == "add-phone":
        from cura.setup.add_phone import run as phone_run
        sys.exit(phone_run())


    if args.command == "console":
        from cura.console import main as console_main
        sys.argv = ["cura.console"]
        if args.name:
            sys.argv += ["--name", args.name]
        if args.demo:
            sys.argv.append("--demo")
        if args.medications:
            sys.argv += ["--medications"] + args.medications
        console_main()

    elif args.command == "webhook":
        from cura.comms.responder import CuraResponder
        from cura.comms.webhook import create_app
        responder = CuraResponder()
        app = create_app(responder=responder, elder_name=args.elder_name)
        print(f"Cura webhook server starting on port {args.port}")
        print(f"Configure Twilio to point to: http://your-server:{args.port}/voice/inbound")
        app.run(host="0.0.0.0", port=args.port)

    elif args.command == "run":
        _run_scheduled(args.config, args.dry_run)

    else:
        parser.print_help()
        print("\nQuick start:")
        print("  python -m cura console --name Margaret          # Chat with Cura")
        print("  python -m cura console --name Margaret --demo   # See a demo check-in")



def _default_config_path():
    """The config the wizard wrote, if there is exactly one obvious choice."""
    import json
    from pathlib import Path as _P
    state = _P.home() / ".cura" / "setup-progress.json"
    try:
        p = json.loads(state.read_text()).get("config_path")
        if p and _P(p).exists():
            return p
    except Exception:
        pass
    found = sorted((_P.home() / ".cura").glob("*.json"))
    found = [f for f in found if f.name != "setup-progress.json"]
    return str(found[0]) if len(found) == 1 else None


def _preview(config_path: str) -> None:
    """Print both check-ins and return. Never starts a scheduler."""
    import json as _json
    with open(config_path) as f:
        data = _json.load(f)
    data.pop("twilio", None)

    from cura.pulse.eldercare_pulse import ElderProfile, EldercarePulseConfig
    from cura.pulse.checkin_composer import CheckinComposer

    profile = ElderProfile(
        name=data.get("name", ""), preferred_name=data.get("preferred_name", ""),
        phone=data.get("phone", ""), medications=data.get("medications", []),
        emergency_contacts=data.get("emergency_contacts", []),
        primary_caregiver=data.get("primary_caregiver", {}),
        address=data.get("address", ""),
        morning_time=data.get("morning_time", 8),
        evening_time=data.get("evening_time", 20),
    )
    cfg = EldercarePulseConfig(profile)
    composer = CheckinComposer()
    who = profile.display_name

    print()
    print(f"  This is what {who} will hear. Nothing is being dialled.")
    print()
    print(f"  In the morning, around {profile.morning_time}:00 —")
    print()
    for msg in composer.compose_morning(cfg).all_messages:
        print(f"      Cura:  {msg}")
    print()
    try:
        evening = composer.compose_evening(cfg).all_messages
    except Exception:
        evening = []
    if evening:
        print(f"  In the evening, around {profile.evening_time}:00 —")
        print()
        for msg in evening:
            print(f"      Cura:  {msg}")
        print()
    print("  If that sounds right, you're ready.")
    print()


def _run_scheduled(config_path: str, dry_run: bool = False) -> None:
    """Start scheduled daily check-ins."""
    import json
    from pathlib import Path

    path = Path(config_path)
    if not path.exists():
        print(f"Config file not found: {config_path}")
        print("\nCreate a JSON file like this:")
        print(json.dumps({
            "name": "Margaret Chen",
            "preferred_name": "Margaret",
            "phone": "+15551234567",
            "medications": [
                {"name": "Lisinopril", "time": "morning"},
                {"name": "Metformin", "time": "morning"},
            ],
            "emergency_contacts": [
                {"name": "Sarah Chen", "phone": "+15559876543", "relation": "daughter"},
            ],
            "primary_caregiver": {"name": "Sarah Chen", "phone": "+15559876543"},
            "address": "123 Elm Street, Springfield, IL",
            "morning_time": 8,
            "evening_time": 20,
            "twilio": {
                "account_sid": "your_sid",
                "auth_token": "your_token",
                "phone_number": "+15550001234",
            },
        }, indent=2))
        sys.exit(1)

    with open(path) as f:
        data = json.load(f)

    from cura.pulse.eldercare_pulse import ElderProfile, EldercarePulseConfig
    from cura.pulse.checkin_composer import CheckinComposer
    from cura.comms.voice import CuraVoice
    from cura.comms.responder import CuraResponder

    twilio_config = data.pop("twilio", {})

    profile = ElderProfile(
        name=data.get("name", ""),
        preferred_name=data.get("preferred_name", ""),
        phone=data.get("phone", ""),
        medications=data.get("medications", []),
        emergency_contacts=data.get("emergency_contacts", []),
        primary_caregiver=data.get("primary_caregiver", {}),
        address=data.get("address", ""),
        morning_time=data.get("morning_time", 8),
        evening_time=data.get("evening_time", 20),
    )

    pulse_config = EldercarePulseConfig(profile)
    composer = CheckinComposer()
    voice = CuraVoice(
        account_sid=twilio_config.get("account_sid", ""),
        auth_token=twilio_config.get("auth_token", ""),
        from_number=twilio_config.get("phone_number", ""),
        dry_run=dry_run,
    )

    name = profile.display_name
    morning_h = profile.morning_time
    evening_h = profile.evening_time

    print(f"Cura — caring for {name}")
    print(f"  Morning check-in: {morning_h}:00")
    print(f"  Evening check-in: {evening_h}:00")
    print(f"  Phone: {profile.phone}")
    print(f"  Dry run: {dry_run}")
    print()

    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        print("APScheduler not installed. Install it to run scheduled calls:")
        print("  pip install APScheduler")
        print()
        print("For now, here's what a morning check-in would say:")
        print()
        checkin = composer.compose_morning(pulse_config)
        for msg in checkin.all_messages:
            print(f"  Cura: {msg}")
        sys.exit(0)

    import asyncio

    async def do_morning():
        checkin = composer.compose_morning(pulse_config)
        await voice.call(
            to_number=profile.phone,
            messages=checkin.all_messages,
            gather_response=True,
            status_callback="/voice/checkin-response",
        )
        print(f"[{_now()}] Morning check-in sent to {name}")

    async def do_evening():
        checkin = composer.compose_evening(pulse_config)
        await voice.call(
            to_number=profile.phone,
            messages=checkin.all_messages,
            gather_response=True,
            status_callback="/voice/evening-response",
        )
        print(f"[{_now()}] Evening check-in sent to {name}")

    def morning_job():
        asyncio.run(do_morning())

    def evening_job():
        asyncio.run(do_evening())

    scheduler = BlockingScheduler()
    scheduler.add_job(morning_job, "cron", hour=morning_h, minute=0)
    scheduler.add_job(evening_job, "cron", hour=evening_h, minute=0)

    print(f"Cura is running. She'll call {name} every day.")
    print("Press Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print(f"\nCura is resting. {name} will hear from her again soon.")


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M")


if __name__ == "__main__":
    main()
