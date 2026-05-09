"""Caregiver Daily Summary — the bridge across the distance.

Every evening, the caregiver gets a text. Not a medical report.
A human summary of how their loved one's day went.

"Reached: morning and evening. Took his meds. Laughed at the
word game. Mentioned his back is bothering him again.
Steps were below usual. He asked about your visit."

The caregiver reads this from 4 states away and knows:
Dad is okay. Someone is looking after him. And he misses me.

Delivered via SMS (Twilio). One text per day. Brief, warm,
honest. Flags concerns without causing panic.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from cura.memory.companion_memory import CompanionMemory

logger = logging.getLogger(__name__)


@dataclass
class DailySummary:
    """A daily summary for the caregiver."""
    elder_name: str
    date: str
    morning_reached: bool = False
    evening_reached: bool = False
    medications_confirmed: int = 0
    medications_total: int = 0
    mood: str = ""
    mood_context: str = ""
    concerns: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)
    people_mentioned: list[str] = field(default_factory=list)
    steps: int | None = None
    steps_vs_usual: str = ""
    scam_alerts: int = 0
    notes: str = ""

    def format_sms(self) -> str:
        """Format as an SMS-length summary."""
        parts = [f"Cura — {self.elder_name}'s Day"]

        reached = []
        if self.morning_reached:
            reached.append("morning")
        if self.evening_reached:
            reached.append("evening")
        if reached:
            parts.append(f"Reached: {' & '.join(reached)} ✓")
        else:
            parts.append("⚠ Could not reach today")

        if self.medications_total > 0:
            if self.medications_confirmed == self.medications_total:
                parts.append(f"Meds: all confirmed ✓")
            else:
                parts.append(f"Meds: {self.medications_confirmed}/{self.medications_total} confirmed")

        if self.mood:
            mood_str = f"Mood: {self.mood}"
            if self.mood_context:
                mood_str += f" ({self.mood_context})"
            parts.append(mood_str)

        if self.steps is not None:
            step_str = f"Steps: {self.steps:,}"
            if self.steps_vs_usual:
                step_str += f" ({self.steps_vs_usual})"
            parts.append(step_str)

        for highlight in self.highlights[:2]:
            parts.append(f"• {highlight}")

        if self.people_mentioned:
            parts.append(f"Mentioned: {', '.join(self.people_mentioned)}")

        for concern in self.concerns[:2]:
            parts.append(f"⚠ {concern}")

        if self.scam_alerts > 0:
            parts.append(f"🛡 {self.scam_alerts} suspicious contact(s) flagged")

        if self.notes:
            parts.append(self.notes)

        return "\n".join(parts)

    def format_detailed(self) -> str:
        """Format as a longer email/dashboard summary."""
        parts = [
            f"Daily Care Summary — {self.elder_name}",
            f"Date: {self.date}",
            "=" * 50,
        ]

        parts.append(f"\nCHECK-INS:")
        parts.append(f"  Morning: {'Reached ✓' if self.morning_reached else 'Not reached ✗'}")
        parts.append(f"  Evening: {'Reached ✓' if self.evening_reached else 'Not reached ✗'}")

        if self.medications_total > 0:
            status = "All confirmed ✓" if self.medications_confirmed == self.medications_total else f"{self.medications_confirmed}/{self.medications_total} confirmed"
            parts.append(f"\nMEDICATIONS: {status}")

        if self.mood:
            parts.append(f"\nMOOD: {self.mood}")
            if self.mood_context:
                parts.append(f"  Context: {self.mood_context}")

        if self.steps is not None:
            parts.append(f"\nACTIVITY: {self.steps:,} steps {f'({self.steps_vs_usual})' if self.steps_vs_usual else ''}")

        if self.highlights:
            parts.append(f"\nHIGHLIGHTS:")
            for h in self.highlights:
                parts.append(f"  • {h}")

        if self.people_mentioned:
            parts.append(f"\nPEOPLE MENTIONED: {', '.join(self.people_mentioned)}")

        if self.concerns:
            parts.append(f"\nCONCERNS:")
            for c in self.concerns:
                parts.append(f"  ⚠ {c}")

        if self.scam_alerts:
            parts.append(f"\nSCAM DEFENSE: {self.scam_alerts} suspicious contact(s) flagged and handled")

        parts.append(f"\n— Cura")
        return "\n".join(parts)


class CaregiverSummaryBuilder:
    """Build a daily summary from the day's check-in data and memory.

    Pulls from:
      - Check-in results (reached, medication confirmed)
      - Companion memory (observations, mood, people)
      - Wearable data (steps, heart rate)
      - Scam shield (alerts)
    """

    def build(
        self,
        elder_name: str,
        memory: CompanionMemory | None = None,
        checkin_results: list[dict] | None = None,
        wearable_data: dict | None = None,
        scam_alerts: int = 0,
        medications_total: int = 0,
    ) -> DailySummary:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        summary = DailySummary(elder_name=elder_name, date=today)

        if checkin_results:
            for cr in checkin_results:
                if cr.get("check_type") == "morning" and cr.get("reached"):
                    summary.morning_reached = True
                if cr.get("check_type") == "evening" and cr.get("reached"):
                    summary.evening_reached = True
                if cr.get("medication_confirmed"):
                    summary.medications_confirmed += 1
        summary.medications_total = medications_total

        if memory:
            today_obs = [o for o in memory.observations if o.timestamp.startswith(today)]

            for obs in today_obs:
                if obs.category == "joy":
                    summary.highlights.append(obs.content)
                elif obs.category == "concern":
                    summary.concerns.append(obs.content)
                elif obs.category == "health":
                    summary.concerns.append(obs.content)
                elif obs.category in ("daily_life", "family"):
                    summary.highlights.append(obs.content)

                for person in obs.people_mentioned:
                    if person not in summary.people_mentioned:
                        summary.people_mentioned.append(person)

            today_moods = [m for m in memory.mood_history if m.timestamp.startswith(today)]
            if today_moods:
                summary.mood = today_moods[-1].mood
                summary.mood_context = today_moods[-1].context

        if wearable_data:
            summary.steps = wearable_data.get("steps")
            baseline_steps = wearable_data.get("baseline_steps", 3000)
            if summary.steps is not None:
                if summary.steps < baseline_steps * 0.6:
                    summary.steps_vs_usual = "below usual"
                    summary.concerns.append("Activity lower than usual today")
                elif summary.steps > baseline_steps * 1.3:
                    summary.steps_vs_usual = "more active than usual"
                else:
                    summary.steps_vs_usual = "normal"

        summary.scam_alerts = scam_alerts

        if not summary.morning_reached and not summary.evening_reached:
            summary.concerns.insert(0, "Could not reach today — consider calling")

        return summary
