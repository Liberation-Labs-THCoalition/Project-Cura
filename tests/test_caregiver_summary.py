"""Tests for caregiver daily summary."""
from __future__ import annotations

from cura.comms.caregiver_summary import CaregiverSummaryBuilder, DailySummary
from cura.memory.companion_memory import CompanionMemory


class TestDailySummary:
    def test_sms_format(self):
        summary = DailySummary(
            elder_name="Dad",
            date="2026-05-08",
            morning_reached=True,
            evening_reached=True,
            medications_confirmed=2,
            medications_total=2,
            mood="good",
            mood_context="laughed at the word game",
            steps=3200,
            steps_vs_usual="normal",
            highlights=["asked Cura to read more of his book"],
            people_mentioned=["you"],
        )
        sms = summary.format_sms()
        assert "Dad" in sms
        assert "morning" in sms
        assert "Meds: all confirmed" in sms
        assert "good" in sms
        assert "3,200" in sms
        assert "book" in sms

    def test_sms_unreached(self):
        summary = DailySummary(
            elder_name="Dad", date="2026-05-08",
            morning_reached=False, evening_reached=False,
        )
        sms = summary.format_sms()
        assert "Could not reach" in sms

    def test_sms_with_concerns(self):
        summary = DailySummary(
            elder_name="Dad", date="2026-05-08",
            morning_reached=True, evening_reached=True,
            concerns=["mentioned back pain again"],
        )
        sms = summary.format_sms()
        assert "back pain" in sms

    def test_sms_with_scam_alert(self):
        summary = DailySummary(
            elder_name="Dad", date="2026-05-08",
            morning_reached=True, evening_reached=True,
            scam_alerts=1,
        )
        sms = summary.format_sms()
        assert "suspicious" in sms.lower()

    def test_detailed_format(self):
        summary = DailySummary(
            elder_name="Dad", date="2026-05-08",
            morning_reached=True, evening_reached=True,
            medications_confirmed=2, medications_total=2,
            mood="content", highlights=["talked about the garden"],
        )
        detailed = summary.format_detailed()
        assert "Daily Care Summary" in detailed
        assert "Reached" in detailed
        assert "garden" in detailed
        assert "Cura" in detailed


class TestSummaryBuilder:
    def test_build_from_checkins(self):
        builder = CaregiverSummaryBuilder()
        summary = builder.build(
            "Dad",
            checkin_results=[
                {"check_type": "morning", "reached": True, "medication_confirmed": True},
                {"check_type": "evening", "reached": True, "medication_confirmed": True},
            ],
            medications_total=2,
        )
        assert summary.morning_reached
        assert summary.evening_reached
        assert summary.medications_confirmed == 2

    def test_build_from_memory(self):
        memory = CompanionMemory(elder_name="Dad")
        memory.add_observation("Garden tomatoes coming in", "joy")
        memory.add_observation("Back hurting again", "concern")
        memory.record_mood("good", "proud of garden")

        builder = CaregiverSummaryBuilder()
        summary = builder.build("Dad", memory=memory, checkin_results=[
            {"check_type": "morning", "reached": True},
        ])
        assert "tomatoes" in summary.highlights[0]
        assert any("Back" in c for c in summary.concerns)
        assert summary.mood == "good"

    def test_build_from_wearable(self):
        builder = CaregiverSummaryBuilder()
        summary = builder.build(
            "Dad",
            wearable_data={"steps": 1200, "baseline_steps": 3000},
        )
        assert summary.steps == 1200
        assert summary.steps_vs_usual == "below usual"
        assert any("Activity" in c for c in summary.concerns)

    def test_unreached_concern(self):
        builder = CaregiverSummaryBuilder()
        summary = builder.build("Dad")
        assert any("Could not reach" in c for c in summary.concerns)

    def test_full_day_sms(self):
        memory = CompanionMemory(elder_name="Dad")
        memory.add_observation("Laughed at the rhyming game", "joy")
        memory.add_observation("Asked about your visit", "family", people=["Thomas"])
        memory.record_mood("happy", "good spirits today")

        builder = CaregiverSummaryBuilder()
        summary = builder.build(
            "Dad",
            memory=memory,
            checkin_results=[
                {"check_type": "morning", "reached": True, "medication_confirmed": True},
                {"check_type": "evening", "reached": True, "medication_confirmed": True},
            ],
            wearable_data={"steps": 3200, "baseline_steps": 3000},
            medications_total=2,
        )

        sms = summary.format_sms()
        assert "Dad" in sms
        assert "morning" in sms
        assert "happy" in sms
        assert "Thomas" in sms
