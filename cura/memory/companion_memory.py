"""Companion Memory — Cura remembers Margaret.

Not medical records. Not medication logs. The human things.

What she talked about. What made her laugh. What worried her.
Who she mentioned. What's coming up. What she was looking
forward to. What book they were reading together.

So the next call isn't "Good morning, Margaret. How are you?"
It's "Good morning, Margaret. How was Sarah's birthday
yesterday? Did she like the gift you told me about?"

That's the difference between a system and a companion.

Architecture:
  - Observations: raw facts extracted from conversations
  - Topics: things Margaret cares about, tracked over time
  - People: her world — family, friends, neighbors, doctors
  - Events: upcoming and past, mentioned in conversation
  - Mood: emotional trajectory, not diagnoses
  - Continuity: what was Cura doing with Margaret?
    (reading a book, working through home safety questions, etc.)

Storage: JSON file per elder. No cloud, no database.
One file, human-readable, belongs to the family.
"""
from __future__ import annotations

import hashlib
import json
import os
import unicodedata
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Observation:
    """Something Margaret said or Cura noticed."""
    timestamp: str
    source: str  # "morning_checkin", "evening_checkin", "inbound_call", "sms"
    content: str
    category: str  # "health", "family", "mood", "daily_life", "concern", "joy", "request"
    people_mentioned: list[str] = field(default_factory=list)
    follow_up: bool = False


@dataclass
class Person:
    """Someone in Margaret's world."""
    name: str
    relation: str  # "daughter", "grandson", "neighbor", "doctor", "friend"
    last_mentioned: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class UpcomingEvent:
    """Something Margaret mentioned is coming up."""
    description: str
    date: str  # YYYY-MM-DD or "soon" or "this week"
    mentioned_on: str
    people_involved: list[str] = field(default_factory=list)
    reminded: bool = False


@dataclass
class MoodEntry:
    """How Margaret seemed during a conversation."""
    timestamp: str
    mood: str  # "happy", "lonely", "worried", "tired", "energetic", "sad", "content"
    context: str = ""


@dataclass
class Continuity:
    """Ongoing activities Cura and Margaret share."""
    activity: str  # "reading_book", "home_safety_assessment", "word_games"
    state: dict[str, Any] = field(default_factory=dict)
    last_updated: str = ""


@dataclass
class CompanionMemory:
    """Everything Cura remembers about one elder."""
    elder_name: str
    created: str = ""
    last_updated: str = ""
    observations: list[Observation] = field(default_factory=list)
    people: list[Person] = field(default_factory=list)
    upcoming_events: list[UpcomingEvent] = field(default_factory=list)
    mood_history: list[MoodEntry] = field(default_factory=list)
    continuity: list[Continuity] = field(default_factory=list)
    topics_of_interest: list[str] = field(default_factory=list)
    conversation_count: int = 0

    def add_observation(self, content: str, category: str, source: str = "checkin",
                        people: list[str] | None = None, follow_up: bool = False) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.observations.append(Observation(
            timestamp=now, source=source, content=content,
            category=category, people_mentioned=people or [],
            follow_up=follow_up,
        ))
        self.last_updated = now

        for name in (people or []):
            self._ensure_person(name)

    def add_person(self, name: str, relation: str, note: str = "") -> None:
        existing = self._find_person(name)
        if existing:
            if note:
                existing.notes.append(note)
            existing.last_mentioned = datetime.now(timezone.utc).isoformat()
        else:
            self.people.append(Person(
                name=name, relation=relation,
                last_mentioned=datetime.now(timezone.utc).isoformat(),
                notes=[note] if note else [],
            ))

    def add_event(self, description: str, date: str, people: list[str] | None = None) -> None:
        self.upcoming_events.append(UpcomingEvent(
            description=description, date=date,
            mentioned_on=datetime.now(timezone.utc).isoformat(),
            people_involved=people or [],
        ))

    def record_mood(self, mood: str, context: str = "") -> None:
        self.mood_history.append(MoodEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            mood=mood, context=context,
        ))

    def update_continuity(self, activity: str, **state) -> None:
        for c in self.continuity:
            if c.activity == activity:
                c.state.update(state)
                c.last_updated = datetime.now(timezone.utc).isoformat()
                return
        self.continuity.append(Continuity(
            activity=activity, state=state,
            last_updated=datetime.now(timezone.utc).isoformat(),
        ))

    def recent_observations(self, days: int = 7, category: str = "") -> list[Observation]:
        """Observations from the last `days` days.

        `cutoff` was computed and never compared, so `days` did nothing and this
        returned the last 20 observations of any age. The caller that matters is
        conversation_context(days=3), which labels the result "Recent
        conversations" — so a worry from March could be handed to Cura as
        something she said this week, and Cura would follow up on it as though
        it were current.

        EldercarePulseConfig.recent_checkins does this correctly four lines from
        its own equivalent. The pattern was already in the codebase.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        recent = []
        for obs in reversed(self.observations):
            if category and obs.category != category:
                continue
            # An observation with no timestamp is of unknown age. Keep it and
            # let it be seen rather than silently dropping it -- but it must not
            # be the reason `days` appears to work.
            if obs.timestamp and obs.timestamp < cutoff:
                break        # observations are appended in order; older follow
            recent.append(obs)
            if len(recent) >= 20:
                break
        return recent

    def pending_followups(self) -> list[Observation]:
        return [o for o in self.observations if o.follow_up]

    def recent_mood(self, n: int = 5) -> list[MoodEntry]:
        return self.mood_history[-n:]

    def get_person(self, name: str) -> Person | None:
        return self._find_person(name)

    def unreferenced_events(self) -> list[UpcomingEvent]:
        return [e for e in self.upcoming_events if not e.reminded]

    def mark_event_reminded(self, description: str) -> None:
        for e in self.upcoming_events:
            if e.description == description:
                e.reminded = True

    def generate_context(self) -> str:
        """Generate conversation context for the check-in composer.

        This is what Cura 'knows' going into a conversation.
        """
        parts = []

        recent = self.recent_observations(days=3)
        if recent:
            parts.append("Recent conversations:")
            for obs in recent[:5]:
                parts.append(f"  - [{obs.category}] {obs.content}")

        followups = self.pending_followups()
        if followups:
            parts.append("Follow up on:")
            for f in followups[:3]:
                parts.append(f"  - {f.content}")

        events = self.unreferenced_events()
        if events:
            parts.append("Upcoming events:")
            for e in events[:3]:
                parts.append(f"  - {e.description} ({e.date})")

        moods = self.recent_mood(3)
        if moods:
            mood_str = ", ".join(m.mood for m in moods)
            parts.append(f"Recent mood: {mood_str}")

        for c in self.continuity:
            if c.activity == "reading_book":
                book = c.state.get("title", "a book")
                pos = c.state.get("position", 0)
                parts.append(f"Currently reading: {book} (passage {pos})")

        people_recent = sorted(
            [p for p in self.people if p.last_mentioned],
            key=lambda p: p.last_mentioned, reverse=True,
        )[:5]
        if people_recent:
            parts.append("People mentioned recently:")
            for p in people_recent:
                parts.append(f"  - {p.name} ({p.relation})")

        return "\n".join(parts) if parts else "No prior conversation history."

    def _find_person(self, name: str) -> Person | None:
        name_lower = name.lower()
        for p in self.people:
            if p.name.lower() == name_lower:
                return p
        return None

    def _ensure_person(self, name: str) -> None:
        if not self._find_person(name):
            self.people.append(Person(
                name=name, relation="unknown",
                last_mentioned=datetime.now(timezone.utc).isoformat(),
            ))



def _safe_stem(elder_name: str) -> str:
    """Turn a person's name into a filename that cannot leave the store.

    The old version was `name.lower().replace(" ", "_")`, which is not a
    sanitiser -- it only handled spaces. An elder_name of "../../escaped" wrote
    to /tmp/escaped.json, outside the store entirely, and elder_name is not
    always ours: it comes from setup, and in the facility case it would come
    from whoever enters the resident list.

    Kept deliberately narrow: lowercase letters, digits, underscore, hyphen.
    Everything else becomes an underscore, so separators and dots cannot
    survive to be interpreted as a path.

    Accents are folded rather than destroyed, so "José García" becomes
    jose_garcia and not jos__garc_a. Cura ships in Spanish; a household should
    not find their own name mangled in their own filesystem.

    NOTE: distinct names can still collide ("José García" and "Jose Garcia"
    both fold to jose_garcia), which would silently merge two people's
    memories. Harmless in a single-elder household, NOT harmless in the
    facility case. Fixing it properly needs a stable resident id rather than a
    name, which is a data-model decision -- tracked with the PRN work.
    """
    if not elder_name or not elder_name.strip():
        raise ValueError("elder_name is empty; there is nobody to store")
    folded = unicodedata.normalize("NFKD", elder_name.strip().lower())
    stem = "".join(
        ch if (ch.isalnum() and ch.isascii()) or ch in "_-" else "_"
        for ch in folded
        if not unicodedata.combining(ch)
    ).strip("_")
    if not stem:
        # A name in a non-Latin script folds to nothing. Refusing here would
        # mean Cura cannot remember anyone named in Chinese, Arabic, Hebrew,
        # Greek or Cyrillic -- a hard failure for a whole class of households,
        # in a product whose entire job is remembering. Fall back to a stable
        # digest of the name instead: unreadable on disk, but deterministic,
        # contained, and the person's real name is preserved inside the file.
        digest = hashlib.sha256(elder_name.strip().encode("utf-8")).hexdigest()
        return f"elder_{digest[:16]}"
    return stem


class MemoryStore:
    """Persist companion memory to disk.

    One JSON file per elder. Human-readable. Belongs to the family.
    No cloud, no database, no third-party storage.
    """

    def __init__(self, data_dir: str = "") -> None:
        self._dir = Path(data_dir) if data_dir else Path.home() / ".cura" / "memory"

    def _path_for(self, elder_name: str) -> Path:
        """Resolve one elder's file, and verify it lands inside the store.

        The sanitiser above should make this impossible to violate; the check
        stays anyway, because a containment rule enforced in one place is
        cheaper to trust than one argued from the sanitiser's correctness.
        """
        path = self._dir / f"{_safe_stem(elder_name)}.json"
        root = self._dir.resolve()
        if not str(path.resolve()).startswith(str(root) + os.sep):
            raise ValueError(
                f"refusing to write {elder_name!r} outside the memory store")
        return path

    def _harden(self, path: Path) -> None:
        """Memory holds what she said, who visited, and how she seemed."""
        try:
            os.chmod(self._dir, 0o700)
            os.chmod(path, 0o600)
        except OSError:
            pass

    def save(self, memory: CompanionMemory) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path_for(memory.elder_name)

        data = asdict(memory)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        self._harden(path)
        logger.info("Memory saved: %s (%d observations)", path, len(memory.observations))
        return path

    def load(self, elder_name: str) -> CompanionMemory:
        path = self._path_for(elder_name)

        if not path.exists():
            return CompanionMemory(
                elder_name=elder_name,
                created=datetime.now(timezone.utc).isoformat(),
            )

        data = json.loads(path.read_text())
        memory = CompanionMemory(elder_name=data.get("elder_name", elder_name))
        memory.created = data.get("created", "")
        memory.last_updated = data.get("last_updated", "")
        memory.conversation_count = data.get("conversation_count", 0)
        memory.topics_of_interest = data.get("topics_of_interest", [])

        for obs in data.get("observations", []):
            memory.observations.append(Observation(**obs))
        for p in data.get("people", []):
            memory.people.append(Person(**p))
        for e in data.get("upcoming_events", []):
            memory.upcoming_events.append(UpcomingEvent(**e))
        for m in data.get("mood_history", []):
            memory.mood_history.append(MoodEntry(**m))
        for c in data.get("continuity", []):
            memory.continuity.append(Continuity(**c))

        return memory

    def exists(self, elder_name: str) -> bool:
        try:
            return self._path_for(elder_name).exists()
        except ValueError:
            return False
