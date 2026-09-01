"""Eldercare Pulse — the heartbeat of a faithful companion.

Configures the Kintsugi Pulse primitive for eldercare:
  Morning: medication + wellness check
  Midday: activity monitoring (adaptive)
  Evening: daily summary + medication
  Continuous: fall detection + vital sign monitoring
  Weekly: benefits scan + appointment review

The pulse self-modifies based on the elder's patterns:
  - Consistently active at 8am? Delay check to 9am.
  - Missed 3 medication checks? Increase frequency, alert caregiver.
  - Haven't left the house in 5 days? Trigger social outreach.
  - Fall detected? Switch to crisis mode immediately.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


# Which check-in a medication belongs to. Cura only has two delivery slots,
# the morning check-in and the evening one, so every recorded "time" has to
# resolve to one or both of them. Getting this wrong is a dosing error, not a
# wording error: someone with dementia who is told at 6pm that it is time for a
# drug they already took at 9am may well take it a second time.
_MORNING_WORDS = r"\b(?:morning|breakfast|wake|waking|sunrise)\b"
_EVENING_WORDS = r"\b(?:evening|night|bedtime|bed|dinner|supper|sunset)\b"
_BOTH_WORDS = r"\b(?:both|twice|two times|2x|bid)\b"
_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b")


def medication_slots(med: dict[str, Any]) -> set[str]:
    """Return the check-ins a medication should be named in.

    Reads the medication's recorded ``time`` and resolves it to some subset of
    ``{"morning", "evening"}``. Understands words ("morning", "at night",
    "twice daily") and clock times ("8am", "19:30").

    A time that is missing or unreadable resolves to NO check-in, and the
    medication is not named aloud at all.

    An earlier version defaulted the unknown case to the morning check-in,
    reasoning that a missed reminder beats a doubled one. That is right as far
    as it goes and it misses a case: a drug that is actually taken at night,
    recorded with no time, would then be announced at 9am. That is not a missed
    reminder, it is a prompt at the wrong time, and it carries exactly the
    double-dose risk the default was meant to avoid.

    So: unknown timing produces silence, and `unknown_timing_medications` on the
    profile lists what was skipped so a human can be asked. Silence is
    recoverable — the caregiver still gives the medication, as they did before
    Cura existed. A confidently wrong prompt to someone who cannot remember
    whether they already took it is not.

    This is the same rule the fail-state ledger uses for red_proof: no
    observation, no claim.
    """
    raw = str(med.get("time", "") or "").strip().lower()
    if not raw:
        return set()

    slots: set[str] = set()
    if re.search(_BOTH_WORDS, raw):
        return {"morning", "evening"}
    if re.search(_MORNING_WORDS, raw):
        slots.add("morning")
    if re.search(_EVENING_WORDS, raw):
        slots.add("evening")
    if slots:
        return slots

    m = _CLOCK.search(raw)
    if m:
        hour, meridiem = int(m.group(1)), m.group(3)
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        return {"morning" if hour < 12 else "evening"}

    return set()



def unknown_timing_medications(medications) -> list[str]:
    """Medications Cura will NOT mention, because it does not know when they are taken.

    A caregiver must be told this list. Silent omission is safe for dosing and
    unsafe for trust: he has to know Cura is not reminding her about these, or he
    will assume it is.
    """
    return [str(m.get("name", "?")) for m in (medications or [])
            if not medication_slots(m)]

@dataclass
class ElderProfile:
    """The elder's preferences and baseline patterns."""
    name: str
    preferred_name: str = ""  # "Margaret", "Mom", "Mrs. Chen"
    morning_time: int = 8     # hour (24h) for morning check
    evening_time: int = 20    # hour for evening check
    medications: list[dict[str, Any]] = field(default_factory=list)
    emergency_contacts: list[dict[str, str]] = field(default_factory=list)
    primary_caregiver: dict[str, str] = field(default_factory=dict)
    physician: dict[str, str] = field(default_factory=dict)
    phone: str = ""
    address: str = ""
    timezone: str = "America/New_York"
    # Learned patterns
    typical_wake_time: int = 7
    typical_sleep_time: int = 22
    typical_activity_level: float = 0.5  # 0-1
    mobility_baseline: str = "independent"  # independent, assisted, wheelchair
    cognitive_baseline: str = "normal"  # normal, mild_decline, moderate_decline

    @property
    def display_name(self) -> str:
        return self.preferred_name or self.name


@dataclass
class CheckInResult:
    """Result of a check-in interaction with the elder."""
    timestamp: datetime
    check_type: str  # morning, midday, evening, crisis
    reached: bool  # Did we reach them?
    response: str  # What they said (summarized)
    mood_indicator: str = "neutral"  # positive, neutral, concerned, distressed
    medication_confirmed: bool = False
    needs_followup: bool = False
    notes: str = ""


@dataclass
class HealthObservation:
    """A health-relevant observation from sensors or interaction."""
    timestamp: datetime
    source: str  # accelerometer, voice_analysis, wearable, interaction
    observation_type: str  # fall, gait_change, voice_change, inactivity, vital_anomaly
    severity: float  # 0-1
    details: dict[str, Any] = field(default_factory=dict)
    acted_on: bool = False


class EldercarePulseConfig:
    """Configuration for the eldercare pulse cycle."""

    def __init__(self, profile: ElderProfile) -> None:
        self.profile = profile
        self.check_in_history: list[CheckInResult] = []
        self.observations: list[HealthObservation] = []
        self.medication_adherence: dict[str, list[bool]] = {}
        self.days_since_outing: int = 0
        self.missed_checkins_this_week: int = 0

    def record_checkin(self, result: CheckInResult) -> None:
        self.check_in_history.append(result)
        if not result.reached:
            self.missed_checkins_this_week += 1
        if result.medication_confirmed:
            today = result.timestamp.strftime("%Y-%m-%d")
            self.medication_adherence.setdefault(today, []).append(True)

    def record_observation(self, obs: HealthObservation) -> None:
        self.observations.append(obs)

    @property
    def recent_checkins(self) -> list[CheckInResult]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        return [c for c in self.check_in_history if c.timestamp >= cutoff]

    @property
    def recent_observations(self) -> list[HealthObservation]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        return [o for o in self.observations if o.timestamp >= cutoff]

    @property
    def adherence_rate_7d(self) -> float:
        """Medication adherence rate over the last 7 days."""
        recent = self.recent_checkins
        confirmed = sum(1 for c in recent if c.medication_confirmed)
        total = sum(1 for c in recent if c.check_type in ("morning", "evening"))
        return confirmed / max(total, 1)

    @property
    def needs_social_outreach(self) -> bool:
        return self.days_since_outing >= 5

    @property
    def needs_elevated_monitoring(self) -> bool:
        return (
            self.missed_checkins_this_week >= 3
            or self.adherence_rate_7d < 0.5
            or any(o.severity >= 0.7 for o in self.recent_observations)
        )

    def generate_morning_greeting(self) -> str:
        """Generate a warm, personalized morning greeting."""
        name = self.profile.display_name
        greetings = [
            f"Good morning, {name}. How are you feeling today?",
            f"Morning, {name}. Ready to start the day?",
            f"Hello, {name}. I hope you slept well.",
        ]
        # Rotate based on day
        day_idx = datetime.now().timetuple().tm_yday % len(greetings)
        return greetings[day_idx]

    def medications_for(self, when: str) -> list[dict[str, Any]]:
        """The medications due at the ``when`` check-in ("morning"/"evening")."""
        return [
            m for m in self.profile.medications
            if when in medication_slots(m)
        ]

    def generate_medication_reminder(self, when: str = "morning") -> str:
        """Name the medications due at this check-in, or "" if none are.

        Says no name. Every caller delivers this straight after a greeting
        that has already said it, and hearing "Bob. Bob," back to back is
        what makes a companion stop sounding like a person.

        Names every medication due in the slot. A silently truncated list
        reads as a complete one, and the dose left off the end is the dose
        that gets missed.
        """
        meds = self.medications_for(when)
        if not meds:
            return ""
        med_names = [m.get("name", "medication") for m in meds]
        if len(med_names) == 1:
            return f"It's time for your {med_names[0]}."
        return f"It's time for your {', '.join(med_names[:-1])} and {med_names[-1]}."

    def generate_evening_summary(self) -> str:
        name = self.profile.display_name
        today_checkins = [
            c for c in self.check_in_history
            if c.timestamp.date() == datetime.now(timezone.utc).date()
        ]
        parts = [f"Good evening, {name}."]
        if today_checkins:
            meds_taken = sum(1 for c in today_checkins if c.medication_confirmed)
            parts.append(f"You confirmed {meds_taken} medication check{'s' if meds_taken != 1 else ''} today.")
        evening_meds = self.generate_medication_reminder("evening")
        if evening_meds:
            parts.append(evening_meds)
        parts.append("Is there anything you need before bed?")
        return " ".join(parts)

    def assess_crisis_level(self, observation: HealthObservation) -> str:
        """Determine response level for a health observation.

        Returns: 'monitor', 'checkin', 'alert_caregiver', 'crisis'
        """
        if observation.observation_type == "fall" and observation.severity >= 0.7:
            return "crisis"
        if observation.observation_type == "vital_anomaly" and observation.severity >= 0.8:
            return "crisis"
        if observation.severity >= 0.6:
            return "alert_caregiver"
        if observation.severity >= 0.3:
            return "checkin"
        return "monitor"
