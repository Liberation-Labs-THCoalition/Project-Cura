"""Daily Enrichments — quality-of-life features woven into check-ins.

These aren't separate modules — they're additions to Cura's daily
conversations. Each one is a few sentences that make the check-in
richer and Margaret's life a little better.

"Have you had water today?"
"It's going to be 95 degrees — please stay cool."
"What did we talk about yesterday? I'm curious if you remember."
"Want me to read a chapter of your book?"
"Has Whiskers been fed?"

Small things. Huge difference.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class Enrichment:
    """A single enrichment to add to a check-in."""
    category: str
    message: str
    priority: float = 0.5  # higher = more likely to be included
    requires: str = ""  # profile field that must be present


class HydrationNudge:
    """Gentle hydration reminders."""

    MESSAGES = [
        "Have you had a glass of water recently? Staying hydrated helps everything.",
        "Quick reminder to drink some water when you get a chance.",
        "It's easy to forget, but your body needs water. Have a sip for me?",
        "How's your water intake today? Even a small glass helps.",
    ]

    def get(self, profile, weather: dict | None = None) -> Enrichment | None:
        temp = weather.get("temp_f", 70) if weather else 70
        msg = random.choice(self.MESSAGES)
        if temp >= 85:
            msg = f"It's {temp}° today — extra water is important. Please drink plenty."
            return Enrichment("hydration", msg, priority=0.9)
        return Enrichment("hydration", msg, priority=0.4)


class NutritionNudge:
    """Gentle meal reminders."""

    MESSAGES = {
        "morning": "Have you had breakfast? Even something small gives you energy for the day.",
        "midday": "Have you eaten lunch? Your body needs fuel to keep going.",
        "evening": "Did you have a good dinner? Eating well helps you sleep better.",
    }

    def get(self, time_of_day: str) -> Enrichment:
        msg = self.MESSAGES.get(time_of_day, self.MESSAGES["midday"])
        return Enrichment("nutrition", msg, priority=0.4)


class WeatherAlert:
    """Weather-linked health nudges."""

    def get(self, weather: dict) -> Enrichment | None:
        temp = weather.get("temp_f", 70)
        condition = weather.get("condition", "").lower()
        alerts = weather.get("alerts", [])

        if alerts:
            alert_text = alerts[0] if isinstance(alerts[0], str) else alerts[0].get("headline", "")
            return Enrichment(
                "weather_alert",
                f"Weather alert for your area: {alert_text}. Please stay safe.",
                priority=1.0,
            )

        if temp >= 95:
            return Enrichment(
                "weather", f"It's going to be {temp}° today. Please stay indoors, "
                "drink extra water, and keep cool. Heat is dangerous.",
                priority=0.9,
            )
        if temp >= 85:
            return Enrichment(
                "weather", f"It'll be warm today — {temp}°. Please drink extra water.",
                priority=0.6,
            )
        if temp <= 25:
            return Enrichment(
                "weather", f"It's very cold today — {temp}°. Please dress warmly "
                "and be careful of ice on the steps.",
                priority=0.8,
            )
        if "ice" in condition or "snow" in condition or "freezing" in condition:
            return Enrichment(
                "weather", "There's ice or snow expected. Please be very careful "
                "if you go outside, especially on steps and sidewalks.",
                priority=0.8,
            )
        return None


class CognitiveExercise:
    """Gentle cognitive engagement woven into conversation."""

    def recall_check(self, yesterday_topic: str = "") -> Enrichment:
        if yesterday_topic:
            return Enrichment(
                "cognitive",
                f"Yesterday we talked about {yesterday_topic}. "
                "Do you remember what you told me?",
                priority=0.5,
            )
        return Enrichment(
            "cognitive",
            "Can you tell me what you had for breakfast today? "
            "I like hearing about your meals.",
            priority=0.3,
        )

    def word_game(self) -> Enrichment:
        prompts = [
            "Let's play a quick game — can you name three fruits that start with the letter B?",
            "Here's a fun one — what's a word that rhymes with 'cat'? How many can you think of?",
            "Can you count backwards from 20 for me? No rush at all.",
            "Tell me three things you can see from where you're sitting right now.",
            "What's your favorite memory from this time of year?",
        ]
        return Enrichment("cognitive", random.choice(prompts), priority=0.3)


class PetCareReminder:
    """Reminders for pet care — because the pet is family too."""

    def get(self, profile) -> Enrichment | None:
        pet_name = getattr(profile, 'pet_name', '')
        if not pet_name:
            return None
        pet_type = getattr(profile, 'pet_type', 'pet')
        return Enrichment(
            "pet_care",
            f"Has {pet_name} been fed today? And does your {pet_type} "
            f"have fresh water?",
            priority=0.5,
        )


class MovementPrompt:
    """Gentle encouragement to move."""

    MESSAGES = [
        "If you're feeling up to it, even a short walk around the room helps keep you strong.",
        "Have you stretched today? Even some gentle arm raises while sitting are wonderful.",
        "Your body likes to move, even a little. Can you stand up and take a few steps for me?",
        "A little movement goes a long way. How about walking to the window and back?",
    ]

    def get(self) -> Enrichment:
        return Enrichment("movement", random.choice(self.MESSAGES), priority=0.3)


class BookReader:
    """Cura reads to Margaret — companionship + cognitive stimulation.

    Integrates with e-book files (EPUB, TXT) or a reading list.
    Delivers passages via TTS during check-ins.
    """

    def __init__(self):
        self._current_book: str = ""
        self._current_position: int = 0
        self._passages: list[str] = []

    def load_text(self, title: str, text: str, chunk_size: int = 500) -> None:
        """Load a book/text for reading aloud."""
        self._current_book = title
        self._current_position = 0
        # Split into readable chunks at sentence boundaries
        sentences = text.replace('\n', ' ').split('. ')
        chunk = ""
        self._passages = []
        for sentence in sentences:
            if len(chunk) + len(sentence) > chunk_size and chunk:
                self._passages.append(chunk.strip() + ".")
                chunk = sentence
            else:
                chunk += ". " + sentence if chunk else sentence
        if chunk.strip():
            self._passages.append(chunk.strip())

    def get_next_passage(self) -> Enrichment | None:
        if not self._passages or self._current_position >= len(self._passages):
            return None
        passage = self._passages[self._current_position]
        self._current_position += 1
        remaining = len(self._passages) - self._current_position
        return Enrichment(
            "reading",
            f"From '{self._current_book}': {passage} "
            f"... {'Shall I continue?' if remaining > 0 else 'That was the last passage.'}",
            priority=0.6,
        )

    def offer_reading(self) -> Enrichment:
        if self._current_book:
            return Enrichment(
                "reading",
                f"Would you like me to read more of '{self._current_book}'? "
                f"We left off at passage {self._current_position}.",
                priority=0.4,
            )
        return Enrichment(
            "reading",
            "Would you like me to read something to you? "
            "I can read stories, news, or poems.",
            priority=0.3,
        )


class CaregiverBurnoutCheck:
    """Check in on the caregiver — nobody checks on the checkers.

    Runs weekly. Calls the primary caregiver and asks how THEY
    are doing. Because Sarah is spending her evenings worrying
    about Margaret, and nobody asks how she's holding up.
    """

    MESSAGES = [
        "Hi {name}, this is Cura. I wanted to check in on YOU today. "
        "Caregiving is hard work, and you matter too. How are you feeling?",

        "Hello {name}, Cura here. I know you spend a lot of energy "
        "looking after {elder}. Are you getting enough rest?",

        "{name}, this is Cura. Quick check-in — not about {elder} this time, "
        "about you. Is there anything YOU need help with?",

        "Hi {name}. {elder} is lucky to have you. But please make sure "
        "you're taking care of yourself too. How are you doing this week?",
    ]

    RESOURCES = (
        "If you're feeling overwhelmed, the Caregiver Action Network "
        "has a helpline: 1-855-227-3640. You don't have to do this alone."
    )

    def get_checkin_message(self, caregiver_name: str, elder_name: str) -> str:
        msg = random.choice(self.MESSAGES)
        return msg.format(name=caregiver_name, elder=elder_name)

    def get_resource_offer(self) -> str:
        return self.RESOURCES


class HomeSafetyAssessment:
    """Guided home safety check via conversation.

    Not a one-time assessment — periodic questions woven into
    check-ins over several weeks. Covers the major fall/hazard risks.
    """

    QUESTIONS = [
        ("Do you have grab bars in your bathroom, near the toilet and shower?", "fall_prevention"),
        ("Are your hallways and stairways well-lit, especially at night?", "lighting"),
        ("Do you have any loose rugs or cords on the floor you might trip on?", "trip_hazards"),
        ("Are your smoke detectors working? When did you last test them?", "fire_safety"),
        ("Can you reach the things you use every day without climbing on anything?", "accessibility"),
        ("Do you have a flashlight by your bed in case the power goes out?", "emergency_prep"),
        ("Is your hot water temperature set below 120 degrees to prevent burns?", "burn_prevention"),
        ("Do you have non-slip mats in your bathtub or shower?", "fall_prevention"),
        ("Are your medications stored where you can easily read the labels?", "medication_safety"),
        ("Do you have emergency numbers posted somewhere visible?", "emergency_prep"),
    ]

    def __init__(self):
        self._asked_indices: set[int] = set()
        self._concerns: list[tuple[str, str]] = []

    def get_next_question(self) -> Enrichment | None:
        remaining = [
            i for i in range(len(self.QUESTIONS))
            if i not in self._asked_indices
        ]
        if not remaining:
            return None
        idx = remaining[0]
        self._asked_indices.add(idx)
        question, category = self.QUESTIONS[idx]
        return Enrichment(
            "home_safety",
            f"Quick safety question: {question}",
            priority=0.4,
        )

    def record_concern(self, question_idx: int, concern: str) -> None:
        if question_idx < len(self.QUESTIONS):
            self._concerns.append((self.QUESTIONS[question_idx][1], concern))

    def get_summary(self) -> str:
        if not self._concerns:
            return "Home safety assessment complete — no concerns identified."
        return (
            f"Home safety assessment found {len(self._concerns)} concern(s): "
            + "; ".join(f"{cat}: {desc}" for cat, desc in self._concerns)
        )


class SocialMatchmaker:
    """Opt-in social matching for Cura users who want connection.

    Margaret likes gardening and lives in Springfield.
    Dorothy likes gardening and lives 2 miles away.
    "Margaret, I know someone who also loves gardening.
    Would you like me to introduce you?"
    """

    @dataclass
    class UserProfile:
        elder_id: str
        name: str
        interests: list[str]
        location: str
        opted_in: bool = False

    def __init__(self):
        self._profiles: list[SocialMatchmaker.UserProfile] = []

    def register(self, profile: 'SocialMatchmaker.UserProfile') -> None:
        if profile.opted_in:
            self._profiles.append(profile)

    def find_matches(self, elder_id: str, max_results: int = 3) -> list[dict]:
        user = next((p for p in self._profiles if p.elder_id == elder_id), None)
        if not user:
            return []

        matches = []
        for candidate in self._profiles:
            if candidate.elder_id == elder_id:
                continue
            shared = set(user.interests) & set(candidate.interests)
            if shared:
                matches.append({
                    "name": candidate.name,
                    "shared_interests": list(shared),
                    "location": candidate.location,
                })

        matches.sort(key=lambda m: -len(m["shared_interests"]))
        return matches[:max_results]

    def suggest_introduction(self, elder_name: str, match: dict) -> Enrichment:
        shared = " and ".join(match["shared_interests"])
        return Enrichment(
            "social",
            f"{elder_name}, I know someone named {match['name']} who also "
            f"loves {shared}. Would you like me to introduce you?",
            priority=0.5,
        )
