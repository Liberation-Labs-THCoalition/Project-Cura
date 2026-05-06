"""Check-in Composer — assembles a complete check-in from all enrichments.

Picks the most relevant enrichments for each check-in, respects
priority ordering, and keeps messages from being overwhelming.

A morning check-in might include:
  - Greeting + medication reminder (always)
  - Hydration nudge (if hot)
  - Scam education tip (every other day)
  - Cognitive exercise (sometimes)

Never more than 3 enrichments per check-in. The elder shouldn't
feel like they're being interrogated.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from cura.pulse.daily_enrichments import (
    Enrichment,
    HydrationNudge,
    NutritionNudge,
    WeatherAlert,
    CognitiveExercise,
    PetCareReminder,
    MovementPrompt,
    BookReader,
    CaregiverBurnoutCheck,
    HomeSafetyAssessment,
)
from cura.privacy.scam_shield import ScamShield
from cura.sensors.wearable import WearableAnalyzer


@dataclass
class ComposedCheckin:
    """A fully assembled check-in ready for delivery."""
    greeting: str
    medication_reminder: str
    enrichments: list[Enrichment]
    wearable_observations: list[str]
    scam_addition: str | None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def all_messages(self) -> list[str]:
        parts = [self.greeting]
        for obs in self.wearable_observations:
            parts.append(obs)
        if self.medication_reminder:
            parts.append(self.medication_reminder)
        for e in self.enrichments:
            parts.append(e.message)
        if self.scam_addition:
            parts.append(self.scam_addition)
        return parts


class CheckinComposer:
    """Assembles enrichments into coherent check-ins.

    Args:
        max_enrichments: Maximum enrichments per check-in (default 3)
    """

    def __init__(
        self,
        max_enrichments: int = 3,
        wearable_analyzer: WearableAnalyzer | None = None,
    ) -> None:
        self.max_enrichments = max_enrichments
        self.hydration = HydrationNudge()
        self.nutrition = NutritionNudge()
        self.weather = WeatherAlert()
        self.cognitive = CognitiveExercise()
        self.pet_care = PetCareReminder()
        self.movement = MovementPrompt()
        self.book_reader = BookReader()
        self.scam_shield = ScamShield()
        self.home_safety = HomeSafetyAssessment()
        self.wearable = wearable_analyzer
        self._checkin_count = 0

    def compose_morning(
        self,
        pulse_config,
        weather: dict | None = None,
        yesterday_topic: str = "",
    ) -> ComposedCheckin:
        greeting = pulse_config.generate_morning_greeting()
        med_reminder = pulse_config.generate_medication_reminder()

        wearable_obs = self.wearable.analyze_latest() if self.wearable else []

        candidates: list[Enrichment] = []

        if weather:
            alert = self.weather.get(weather)
            if alert:
                candidates.append(alert)

        candidates.append(self.hydration.get(pulse_config.profile, weather))
        candidates.append(self.nutrition.get("morning"))

        if random.random() < 0.4:
            candidates.append(self.cognitive.recall_check(yesterday_topic))

        pet = self.pet_care.get(pulse_config.profile)
        if pet:
            candidates.append(pet)

        enrichments = self._select(candidates)
        scam = self.scam_shield.get_checkin_addition()

        return ComposedCheckin(
            greeting=greeting,
            medication_reminder=med_reminder,
            enrichments=enrichments,
            wearable_observations=wearable_obs,
            scam_addition=scam,
        )

    def compose_evening(
        self,
        pulse_config,
        weather: dict | None = None,
    ) -> ComposedCheckin:
        greeting = pulse_config.generate_evening_summary()

        wearable_obs = self.wearable.analyze_latest() if self.wearable else []

        candidates: list[Enrichment] = []

        candidates.append(self.hydration.get(pulse_config.profile, weather))
        candidates.append(self.nutrition.get("evening"))

        if random.random() < 0.3:
            candidates.append(self.movement.get())

        reading = self.book_reader.offer_reading()
        candidates.append(reading)

        safety_q = self.home_safety.get_next_question()
        if safety_q:
            candidates.append(safety_q)

        enrichments = self._select(candidates)
        scam = self.scam_shield.get_checkin_addition()

        return ComposedCheckin(
            greeting=greeting,
            medication_reminder="",
            enrichments=enrichments,
            wearable_observations=wearable_obs,
            scam_addition=scam,
        )

    def _select(self, candidates: list[Enrichment]) -> list[Enrichment]:
        """Select top enrichments by priority, up to max."""
        candidates.sort(key=lambda e: -e.priority)
        return candidates[:self.max_enrichments]
