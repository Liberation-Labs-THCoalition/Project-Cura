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
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


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

    def generate_medication_reminder(self) -> str:
        name = self.profile.display_name
        meds = self.profile.medications
        if not meds:
            return ""
        med_names = [m.get("name", "medication") for m in meds[:3]]
        if len(med_names) == 1:
            return f"{name}, it's time for your {med_names[0]}."
        return f"{name}, it's time for your {', '.join(med_names[:-1])} and {med_names[-1]}."

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
        if self.profile.medications:
            parts.append(self.generate_medication_reminder())
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
