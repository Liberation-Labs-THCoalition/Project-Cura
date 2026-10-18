"""What Cura is NOT handling for this household, as plain lines (rollout spec C1, 2026-10-17).

Composes checks that already exist. It constructs no escalation machinery and dials nothing."""
import json


def readiness_gaps(config_path) -> list:
    """The gaps a caregiver must be told about, or ["no elder config loaded"] for a config with no elder in it."""
    from cura.__main__ import _load_household
    from cura.comms.escalation import escalation_readiness
    from cura.pulse.eldercare_pulse import ElderProfile, unknown_timing_medications
    try:
        with open(config_path) as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return [f"the config could not be read: {e}"]
    if not (data.get("name") or data.get("phone")):
        return ["no elder config loaded"]
    profile = ElderProfile(
        name=data.get("name", ""), preferred_name=data.get("preferred_name", ""),
        phone=data.get("phone", ""), medications=data.get("medications", []),
        emergency_contacts=data.get("emergency_contacts", []),
        primary_caregiver=data.get("primary_caregiver", {}),
        address=data.get("address", ""),
        morning_time=data.get("morning_time", 8),
        evening_time=data.get("evening_time", 20),
    )
    gaps = list(escalation_readiness(profile))
    household = _load_household(str(config_path))
    if household is not None:
        gaps.extend(household.blocking_problems())
        gaps.extend(household.reportable_gaps())
    for name in unknown_timing_medications(profile.medications):
        gaps.append(f"Cura does not know when {name} is taken and will not name it")
    return gaps
