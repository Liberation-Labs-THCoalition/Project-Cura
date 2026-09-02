"""Tests for companion memory — Cura remembers."""
from __future__ import annotations

import json
import os
import pytest
import tempfile
from pathlib import Path

from cura.memory.companion_memory import (
    CompanionMemory, MemoryStore, Observation, Person, UpcomingEvent,
)


class TestCompanionMemory:
    def test_add_observation(self):
        mem = CompanionMemory(elder_name="Margaret")
        mem.add_observation("Had a lovely walk in the garden", "daily_life")
        assert len(mem.observations) == 1
        assert mem.observations[0].category == "daily_life"

    def test_add_observation_with_people(self):
        mem = CompanionMemory(elder_name="Margaret")
        mem.add_observation("Sarah called today", "family", people=["Sarah"])
        assert len(mem.observations) == 1
        assert "Sarah" in mem.observations[0].people_mentioned
        assert mem._find_person("Sarah") is not None

    def test_add_person(self):
        mem = CompanionMemory(elder_name="Margaret")
        mem.add_person("Sarah", "daughter", "Lives in Springfield")
        assert len(mem.people) == 1
        assert mem.people[0].relation == "daughter"
        assert "Springfield" in mem.people[0].notes[0]

    def test_add_person_updates_existing(self):
        mem = CompanionMemory(elder_name="Margaret")
        mem.add_person("Sarah", "daughter")
        mem.add_person("Sarah", "daughter", "Her birthday is May 15")
        assert len(mem.people) == 1
        assert len(mem.people[0].notes) == 1

    def test_add_event(self):
        mem = CompanionMemory(elder_name="Margaret")
        mem.add_event("Sarah's birthday", "2026-05-15", people=["Sarah"])
        assert len(mem.upcoming_events) == 1
        assert "Sarah" in mem.upcoming_events[0].people_involved

    def test_record_mood(self):
        mem = CompanionMemory(elder_name="Margaret")
        mem.record_mood("happy", "talked about her garden")
        mem.record_mood("worried", "hasn't heard from Tom")
        assert len(mem.mood_history) == 2
        recent = mem.recent_mood(1)
        assert recent[0].mood == "worried"

    def test_update_continuity(self):
        mem = CompanionMemory(elder_name="Margaret")
        mem.update_continuity("reading_book", title="Little Women", position=5)
        assert len(mem.continuity) == 1
        mem.update_continuity("reading_book", position=6)
        assert len(mem.continuity) == 1
        assert mem.continuity[0].state["position"] == 6

    def test_pending_followups(self):
        mem = CompanionMemory(elder_name="Margaret")
        mem.add_observation("Doctor appointment next week", "health", follow_up=True)
        mem.add_observation("Had soup for lunch", "daily_life")
        followups = mem.pending_followups()
        assert len(followups) == 1
        assert "Doctor" in followups[0].content

    def test_unreferenced_events(self):
        mem = CompanionMemory(elder_name="Margaret")
        mem.add_event("Sarah's birthday", "2026-05-15")
        mem.add_event("Doctor visit", "2026-05-20")
        mem.mark_event_reminded("Sarah's birthday")
        unreferenced = mem.unreferenced_events()
        assert len(unreferenced) == 1
        assert "Doctor" in unreferenced[0].description

    def test_generate_context(self):
        mem = CompanionMemory(elder_name="Margaret")
        mem.add_observation("Worried about Whiskers losing weight", "concern",
                           people=["Whiskers"], follow_up=True)
        mem.add_event("Sarah's birthday", "2026-05-15", people=["Sarah"])
        mem.add_person("Sarah", "daughter")
        mem.record_mood("worried", "cat health")
        mem.update_continuity("reading_book", title="Little Women", position=5)

        context = mem.generate_context()
        assert "Whiskers" in context
        assert "Sarah" in context
        assert "birthday" in context
        assert "worried" in context
        assert "Little Women" in context

    def test_empty_context(self):
        mem = CompanionMemory(elder_name="Margaret")
        context = mem.generate_context()
        assert "No prior" in context


class TestMemoryStore:
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(data_dir=tmpdir)
            mem = CompanionMemory(elder_name="Margaret Chen")
            mem.add_observation("Garden is blooming", "daily_life")
            mem.add_person("Sarah", "daughter")
            mem.record_mood("happy")

            path = store.save(mem)
            assert path.exists()

            loaded = store.load("Margaret Chen")
            assert loaded.elder_name == "Margaret Chen"
            assert len(loaded.observations) == 1
            assert loaded.observations[0].content == "Garden is blooming"
            assert len(loaded.people) == 1
            assert loaded.people[0].name == "Sarah"
            assert len(loaded.mood_history) == 1

    def test_load_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(data_dir=tmpdir)
            mem = store.load("Nobody")
            assert mem.elder_name == "Nobody"
            assert len(mem.observations) == 0

    def test_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(data_dir=tmpdir)
            assert not store.exists("Margaret")
            mem = CompanionMemory(elder_name="Margaret")
            store.save(mem)
            assert store.exists("Margaret")

    def test_file_is_human_readable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(data_dir=tmpdir)
            mem = CompanionMemory(elder_name="Margaret")
            mem.add_observation("Loved the roses today", "joy")
            path = store.save(mem)

            raw = path.read_text()
            data = json.loads(raw)
            assert data["elder_name"] == "Margaret"
            assert "roses" in raw


class TestMemoryStoreContainment:
    """elder_name reaches the filesystem, and it is not always ours.

    It comes from setup, and in the facility case from whoever enters the
    resident list. Before this, `name.lower().replace(" ", "_")` was the only
    sanitising, so "../../escaped" wrote to /tmp/escaped.json.
    """

    def _store(self, tmp_path):
        from cura.memory.companion_memory import MemoryStore
        return MemoryStore(data_dir=str(tmp_path / "store")), tmp_path / "store"

    @pytest.mark.parametrize("name", [
        "../../escaped", "../sibling", "a/b/nested", "....//....//x",
        "/etc/passwd", "margaret\x00.json", "..", ".",
    ])
    def test_no_name_escapes_the_store(self, tmp_path, name):
        from cura.memory.companion_memory import CompanionMemory
        store, root = self._store(tmp_path)
        path = store.save(CompanionMemory(elder_name=name))
        assert str(path.resolve()).startswith(str(root.resolve()) + os.sep)

    def test_nothing_is_written_outside_the_store(self, tmp_path):
        from cura.memory.companion_memory import CompanionMemory
        store, root = self._store(tmp_path)
        for name in ["../../escaped", "../sibling", "/etc/passwd"]:
            store.save(CompanionMemory(elder_name=name))
        stray = [p for p in tmp_path.rglob("*.json")
                 if not str(p).startswith(str(root))]
        assert stray == [], f"wrote outside the store: {stray}"

    @pytest.mark.parametrize("name", [
        "Margaret Chen", "José García", "李伟", "Bjørn", "مريم", "Ελένη",
        "Зоя", "O'Brien", "Mary-Anne",
    ])
    def test_every_name_is_storable_and_round_trips(self, tmp_path, name):
        """Refusing a non-Latin name would mean Cura cannot remember a whole
        class of households, in a product whose job is remembering."""
        from cura.memory.companion_memory import CompanionMemory
        store, _ = self._store(tmp_path)
        store.save(CompanionMemory(elder_name=name))
        assert store.exists(name)
        assert store.load(name).elder_name == name, "real name must survive"

    def test_accents_fold_rather_than_shred(self):
        from cura.memory.companion_memory import _safe_stem
        assert _safe_stem("José García") == "jose_garcia"
        assert _safe_stem("Zoë") == "zoe"

    def test_digest_fallback_is_deterministic_and_distinct(self):
        from cura.memory.companion_memory import _safe_stem
        assert _safe_stem("李伟") == _safe_stem("李伟")
        assert _safe_stem("李伟") != _safe_stem("Зоя")

    def test_empty_name_is_refused(self):
        from cura.memory.companion_memory import _safe_stem
        for empty in ["", "   ", "\t"]:
            with pytest.raises(ValueError):
                _safe_stem(empty)

    def test_memory_files_are_private(self, tmp_path):
        """Memory holds what she said, who visited, and how she seemed."""
        from cura.memory.companion_memory import CompanionMemory
        store, root = self._store(tmp_path)
        path = store.save(CompanionMemory(elder_name="Margaret Chen"))
        assert oct(path.stat().st_mode & 0o777) == "0o600"
        assert oct(root.stat().st_mode & 0o777) == "0o700"
