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
from cura.memory.companion_memory import CompanionMemory


@dataclass
class ComposedCheckin:
    """A fully assembled check-in ready for delivery."""
    greeting: str
    medication_reminder: str
    memory_touches: list[str]
    enrichments: list[Enrichment]
    wearable_observations: list[str]
    scam_addition: str | None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def all_messages(self) -> list[str]:
        parts = [self.greeting]
        for touch in self.memory_touches:
            parts.append(touch)
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
        memory: CompanionMemory | None = None,
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
        self.memory = memory
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
        memory_touches = self._memory_touches(pulse_config.profile.display_name)

        return ComposedCheckin(
            greeting=greeting,
            medication_reminder=med_reminder,
            memory_touches=memory_touches,
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
        memory_touches = self._memory_touches(pulse_config.profile.display_name)

        return ComposedCheckin(
            greeting=greeting,
            medication_reminder="",
            memory_touches=memory_touches,
            enrichments=enrichments,
            wearable_observations=wearable_obs,
            scam_addition=scam,
        )

    def _memory_touches(self, name: str) -> list[str]:
        """Generate conversational references from memory.

        These are the human touches that make Cura a companion:
        "How was Sarah's birthday?" instead of a generic greeting.
        Max 2 per check-in — warm, not interrogating.
        """
        if not self.memory:
            return []

        touches = []

        events = self.memory.unreferenced_events()
        for event in events[:1]:
            people = " and ".join(event.people_involved) if event.people_involved else ""
            if people:
                touches.append(
                    f"{name}, you mentioned {event.description} "
                    f"coming up{' with ' + people if people else ''}. How did it go?"
                )
            else:
                touches.append(
                    f"You mentioned {event.description} was coming up. How did it go?"
                )
            self.memory.mark_event_reminded(event.description)

        followups = self.memory.pending_followups()
        for f in followups[:1]:
            if len(touches) >= 2:
                break
            touches.append(f"Last time, you mentioned {f.content}. Any update on that?")
            f.follow_up = False

        if not touches:
            moods = self.memory.recent_mood(3)
            if moods and moods[-1].mood in ("worried", "sad", "lonely"):
                touches.append(
                    f"I've been thinking about you, {name}. "
                    f"How are you feeling today?"
                )

        return touches[:2]

    def _select(self, candidates: list[Enrichment]) -> list[Enrichment]:
        """Select top enrichments by priority, up to max."""
        candidates.sort(key=lambda e: -e.priority)
        return candidates[:self.max_enrichments]
