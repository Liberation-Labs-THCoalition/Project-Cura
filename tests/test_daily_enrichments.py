"""Tests for daily enrichments — quality-of-life check-in features."""
from __future__ import annotations

import pytest
from types import SimpleNamespace

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
    SocialMatchmaker,
)


class TestHydrationNudge:
    def test_normal_temp(self):
        nudge = HydrationNudge()
        result = nudge.get(None, {"temp_f": 72})
        assert result.category == "hydration"
        assert result.priority == 0.4

    def test_hot_day_elevates_priority(self):
        nudge = HydrationNudge()
        result = nudge.get(None, {"temp_f": 95})
        assert result.priority == 0.9
        assert "95°" in result.message

    def test_no_weather_uses_default(self):
        nudge = HydrationNudge()
        result = nudge.get(None)
        assert result is not None
        assert result.category == "hydration"


class TestNutritionNudge:
    def test_morning(self):
        nudge = NutritionNudge()
        result = nudge.get("morning")
        assert "breakfast" in result.message.lower()

    def test_evening(self):
        nudge = NutritionNudge()
        result = nudge.get("evening")
        assert "dinner" in result.message.lower()

    def test_unknown_defaults_to_midday(self):
        nudge = NutritionNudge()
        result = nudge.get("afternoon")
        assert "lunch" in result.message.lower()


class TestWeatherAlert:
    def test_extreme_heat(self):
        alert = WeatherAlert()
        result = alert.get({"temp_f": 100})
        assert result is not None
        assert result.priority == 0.9
        assert "100°" in result.message

    def test_moderate_heat(self):
        alert = WeatherAlert()
        result = alert.get({"temp_f": 88})
        assert result is not None
        assert result.priority == 0.6

    def test_extreme_cold(self):
        alert = WeatherAlert()
        result = alert.get({"temp_f": 20})
        assert result is not None
        assert "cold" in result.message.lower()
        assert result.priority == 0.8

    def test_ice_condition(self):
        alert = WeatherAlert()
        result = alert.get({"temp_f": 35, "condition": "Freezing rain"})
        assert result is not None
        assert result.priority == 0.8

    def test_normal_weather_returns_none(self):
        alert = WeatherAlert()
        result = alert.get({"temp_f": 72, "condition": "Clear"})
        assert result is None

    def test_weather_alert_highest_priority(self):
        alert = WeatherAlert()
        result = alert.get({"temp_f": 72, "alerts": ["Tornado warning"]})
        assert result is not None
        assert result.priority == 1.0
        assert "Tornado warning" in result.message


class TestCognitiveExercise:
    def test_recall_with_topic(self):
        cog = CognitiveExercise()
        result = cog.recall_check("gardening")
        assert "gardening" in result.message
        assert result.priority == 0.5

    def test_recall_without_topic(self):
        cog = CognitiveExercise()
        result = cog.recall_check()
        assert "breakfast" in result.message
        assert result.priority == 0.3

    def test_word_game(self):
        cog = CognitiveExercise()
        result = cog.word_game()
        assert result.category == "cognitive"
        assert len(result.message) > 10


class TestPetCareReminder:
    def test_with_pet(self):
        profile = SimpleNamespace(pet_name="Whiskers", pet_type="cat")
        reminder = PetCareReminder()
        result = reminder.get(profile)
        assert result is not None
        assert "Whiskers" in result.message
        assert "cat" in result.message

    def test_without_pet(self):
        profile = SimpleNamespace()
        reminder = PetCareReminder()
        result = reminder.get(profile)
        assert result is None


class TestMovementPrompt:
    def test_returns_enrichment(self):
        prompt = MovementPrompt()
        result = prompt.get()
        assert result.category == "movement"
        assert result.priority == 0.3


class TestBookReader:
    def test_load_and_read(self):
        reader = BookReader()
        text = ". ".join([f"Sentence {i}" for i in range(30)])
        reader.load_text("Test Book", text, chunk_size=100)
        passage = reader.get_next_passage()
        assert passage is not None
        assert "Test Book" in passage.message
        assert "Shall I continue?" in passage.message

    def test_empty_reader(self):
        reader = BookReader()
        assert reader.get_next_passage() is None

    def test_offer_reading_with_book(self):
        reader = BookReader()
        reader.load_text("My Book", "Some text here.")
        offer = reader.offer_reading()
        assert "My Book" in offer.message

    def test_offer_reading_without_book(self):
        reader = BookReader()
        offer = reader.offer_reading()
        assert "read something to you" in offer.message

    def test_reads_through_all_passages(self):
        reader = BookReader()
        text = ". ".join([f"Sentence number {i}" for i in range(20)])
        reader.load_text("Long Book", text, chunk_size=100)
        count = 0
        while True:
            passage = reader.get_next_passage()
            if passage is None:
                break
            count += 1
        assert count > 1
        last = reader.get_next_passage()
        assert last is None


class TestCaregiverBurnoutCheck:
    def test_message_formatting(self):
        check = CaregiverBurnoutCheck()
        msg = check.get_checkin_message("Sarah", "Margaret")
        assert "Sarah" in msg
        assert "Margaret" in msg or "you" in msg.lower()

    def test_resource_offer(self):
        check = CaregiverBurnoutCheck()
        resource = check.get_resource_offer()
        assert "1-855-227-3640" in resource


class TestHomeSafetyAssessment:
    def test_questions_progress(self):
        assessment = HomeSafetyAssessment()
        q1 = assessment.get_next_question()
        q2 = assessment.get_next_question()
        assert q1 is not None
        assert q2 is not None
        assert q1.message != q2.message

    def test_exhausts_questions(self):
        assessment = HomeSafetyAssessment()
        count = 0
        while assessment.get_next_question() is not None:
            count += 1
        assert count == 10
        assert assessment.get_next_question() is None

    def test_record_concern(self):
        assessment = HomeSafetyAssessment()
        assessment.record_concern(0, "No grab bars in bathroom")
        summary = assessment.get_summary()
        assert "1 concern" in summary
        assert "fall_prevention" in summary

    def test_an_assessment_that_has_done_nothing_does_not_report_clean(self):
        """This test previously asserted that a FRESH assessment — nothing
        asked, nothing answered — reports "no concerns identified". It pinned
        the lie as the specification.

        record_concern has no caller in production: Cura asks about grab bars,
        she answers, handle_speech falls through to "Thank you for sharing that
        with me", and the answer is discarded. So _concerns was always empty and
        the summary always read clean. A caregiver would conclude the bathroom
        had been checked and found safe."""
        summary = HomeSafetyAssessment().get_summary()
        assert "no concerns" not in summary.lower()
        assert "not been asked" in summary.lower() or "have been asked yet" in summary.lower()

    def test_asked_but_unanswered_is_not_a_clean_bill_of_health(self):
        assessment = HomeSafetyAssessment()
        assessment.get_next_question()
        summary = assessment.get_summary()
        assert "no concerns identified" not in summary.lower()
        assert "not a clean bill of health" in summary.lower()

    def test_a_recorded_concern_is_still_reported(self):
        assessment = HomeSafetyAssessment()
        assessment.get_next_question()
        assessment.record_concern(0, "no grab bars in the shower")
        summary = assessment.get_summary()
        assert "grab bars" in summary and "1 concern" in summary


class TestSocialMatchmaker:
    def test_register_and_match(self):
        mm = SocialMatchmaker()
        mm.register(SocialMatchmaker.UserProfile(
            elder_id="1", name="Margaret", interests=["gardening", "reading"],
            location="Springfield", opted_in=True,
        ))
        mm.register(SocialMatchmaker.UserProfile(
            elder_id="2", name="Dorothy", interests=["gardening", "cooking"],
            location="Springfield", opted_in=True,
        ))
        matches = mm.find_matches("1")
        assert len(matches) == 1
        assert matches[0]["name"] == "Dorothy"
        assert "gardening" in matches[0]["shared_interests"]

    def test_no_match_without_opt_in(self):
        mm = SocialMatchmaker()
        mm.register(SocialMatchmaker.UserProfile(
            elder_id="1", name="Margaret", interests=["gardening"],
            location="Springfield", opted_in=True,
        ))
        mm.register(SocialMatchmaker.UserProfile(
            elder_id="2", name="Dorothy", interests=["gardening"],
            location="Springfield", opted_in=False,
        ))
        matches = mm.find_matches("1")
        assert len(matches) == 0

    def test_suggest_introduction(self):
        mm = SocialMatchmaker()
        enrichment = mm.suggest_introduction("Margaret", {
            "name": "Dorothy",
            "shared_interests": ["gardening"],
            "location": "Springfield",
        })
        assert "Margaret" in enrichment.message
        assert "Dorothy" in enrichment.message
        assert "gardening" in enrichment.message
