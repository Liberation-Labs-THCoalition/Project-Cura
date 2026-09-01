"""Build the rehearsal script as data, so both the terminal and the window
render the same thing from one source rather than drifting apart."""
from __future__ import annotations
import json


def preview_lines(config_path: str) -> list[tuple[str, str]]:
    """Return [(kind, text)] where kind is 'heading' or 'line'. No I/O beyond the config."""
    with open(config_path) as f:
        data = json.load(f)
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

    out: list[tuple[str, str]] = []
    out.append(("heading", f"In the morning, around {profile.morning_time}:00"))
    for m in composer.compose_morning(cfg).all_messages:
        out.append(("line", m))
    try:
        evening = composer.compose_evening(cfg).all_messages
    except Exception:
        evening = []
    if evening:
        out.append(("heading", f"In the evening, around {profile.evening_time}:00"))
        for m in evening:
            out.append(("line", m))
    return out
