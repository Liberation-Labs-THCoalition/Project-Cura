"""Tests for wearable integration — body data to care decisions."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from cura.sensors.wearable import (
    WearableReading,
    HealthBaseline,
    WearableAnalyzer,
)
from cura.sensors.fitbit_provider import FitbitProvider
from cura.sensors.gadgetbridge_provider import GadgetbridgeProvider


class TestWearableReading:
    def test_defaults(self):
        r = WearableReading(
            timestamp=datetime.now(timezone.utc),
            source="test",
        )
        assert r.heart_rate is None
        assert r.fall_detected is False
        assert r.sos_pressed is False

    def test_full_reading(self):
        r = WearableReading(
            timestamp=datetime.now(timezone.utc),
            source="fitbit",
            heart_rate=72,
            resting_heart_rate=65,
            steps=4200,
            sleep_minutes=420,
            spo2=96.5,
        )
        assert r.heart_rate == 72
        assert r.spo2 == 96.5


class TestWearableAnalyzer:
    def _analyzer_with_reading(self, **kwargs) -> WearableAnalyzer:
        analyzer = WearableAnalyzer()
        reading = WearableReading(
            timestamp=datetime.now(timezone.utc),
            source="test",
            **kwargs,
        )
        analyzer.add_reading(reading)
        return analyzer

    def test_normal_readings_no_observations(self):
        a = self._analyzer_with_reading(heart_rate=72, spo2=96, sleep_minutes=420)
        obs = a.analyze_latest()
        assert len(obs) == 0

    def test_elevated_heart_rate(self):
        a = WearableAnalyzer(HealthBaseline(avg_resting_hr=70, hr_stddev=5))
        a.add_reading(WearableReading(
            timestamp=datetime.now(timezone.utc),
            source="test", heart_rate=95,
        ))
        obs = a.analyze_latest()
        assert any("heart rate" in o.lower() for o in obs)

    def test_low_heart_rate(self):
        a = WearableAnalyzer(HealthBaseline(avg_resting_hr=70, hr_stddev=5))
        a.add_reading(WearableReading(
            timestamp=datetime.now(timezone.utc),
            source="test", heart_rate=50,
        ))
        obs = a.analyze_latest()
        assert any("heart rate" in o.lower() for o in obs)

    def test_low_spo2(self):
        a = self._analyzer_with_reading(spo2=89)
        obs = a.analyze_latest()
        assert any("oxygen" in o.lower() for o in obs)

    def test_poor_sleep(self):
        a = WearableAnalyzer(HealthBaseline(avg_sleep_minutes=420, sleep_stddev=30))
        a.add_reading(WearableReading(
            timestamp=datetime.now(timezone.utc),
            source="test", sleep_minutes=250,
        ))
        obs = a.analyze_latest()
        assert any("sleep" in o.lower() for o in obs)

    def test_fall_detected(self):
        a = self._analyzer_with_reading(fall_detected=True)
        obs = a.analyze_latest()
        assert any("FALL" in o for o in obs)
        assert a.crisis_detected

    def test_sos_pressed(self):
        a = self._analyzer_with_reading(sos_pressed=True)
        assert a.crisis_detected

    def test_inactivity_check(self):
        a = WearableAnalyzer()
        old = WearableReading(
            timestamp=datetime.now(timezone.utc) - timedelta(hours=13),
            source="test", steps=100,
        )
        a.add_reading(old)
        assert a.check_inactivity(hours=12)

    def test_no_inactivity_when_recent(self):
        a = WearableAnalyzer()
        recent = WearableReading(
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            source="test", steps=100,
        )
        a.add_reading(recent)
        assert not a.check_inactivity(hours=12)

    def test_update_baseline(self):
        a = WearableAnalyzer()
        for i in range(10):
            a.add_reading(WearableReading(
                timestamp=datetime.now(timezone.utc) - timedelta(days=i),
                source="test",
                heart_rate=70 + i,
                resting_heart_rate=65 + i,
                steps=3000 + i * 100,
                sleep_minutes=400 + i * 5,
            ))
        a.update_baseline()
        assert a.baseline.avg_resting_hr != 70.0
        assert a.baseline.avg_steps_per_day != 3000.0


class TestFitbitProviderDryRun:
    @pytest.mark.asyncio
    async def test_fetch_latest(self):
        provider = FitbitProvider(dry_run=True)
        reading = await provider.fetch_latest()
        assert reading is not None
        assert reading.source == "fitbit"
        assert reading.heart_rate == 72

    @pytest.mark.asyncio
    async def test_fetch_daily_summary(self):
        provider = FitbitProvider(dry_run=True)
        reading = await provider.fetch_daily_summary()
        assert reading is not None
        assert reading.steps == 4200
        assert reading.sleep_minutes == 410
        assert reading.spo2 == 96.5


class TestGadgetbridgeProviderDryRun:
    @pytest.mark.asyncio
    async def test_fetch_latest(self):
        provider = GadgetbridgeProvider(dry_run=True)
        reading = await provider.fetch_latest()
        assert reading is not None
        assert reading.source == "gadgetbridge"
        assert reading.heart_rate == 74

    @pytest.mark.asyncio
    async def test_fetch_daily_summary(self):
        provider = GadgetbridgeProvider(dry_run=True)
        reading = await provider.fetch_daily_summary()
        assert reading is not None
        assert reading.steps == 3800
        assert reading.sleep_quality == "fair"


class TestWearableInCheckin:
    """Test that wearable data flows into check-in messages."""

    def test_composer_with_wearable(self):
        from cura.pulse.checkin_composer import CheckinComposer
        from cura.pulse.eldercare_pulse import ElderProfile, EldercarePulseConfig

        profile = ElderProfile(
            name="Margaret", preferred_name="Margaret",
            phone="+15551234567",
            medications=[{"name": "Lisinopril", "time": "morning"}],
            emergency_contacts=[{"name": "Sarah", "phone": "+15559876543"}],
            primary_caregiver={"name": "Sarah", "phone": "+15559876543"},
        )
        config = EldercarePulseConfig(profile)

        analyzer = WearableAnalyzer(HealthBaseline(avg_resting_hr=70, hr_stddev=5))
        analyzer.add_reading(WearableReading(
            timestamp=datetime.now(timezone.utc),
            source="fitbit", heart_rate=95,
        ))

        composer = CheckinComposer(wearable_analyzer=analyzer)
        checkin = composer.compose_morning(config)

        assert len(checkin.wearable_observations) > 0
        assert any("heart rate" in msg.lower() for msg in checkin.all_messages)

    def test_composer_without_wearable(self):
        from cura.pulse.checkin_composer import CheckinComposer
        from cura.pulse.eldercare_pulse import ElderProfile, EldercarePulseConfig

        profile = ElderProfile(
            name="Margaret", preferred_name="Margaret",
            phone="+15551234567",
            medications=[{"name": "Lisinopril", "time": "morning"}],
            emergency_contacts=[{"name": "Sarah", "phone": "+15559876543"}],
            primary_caregiver={"name": "Sarah", "phone": "+15559876543"},
        )
        config = EldercarePulseConfig(profile)

        composer = CheckinComposer()
        checkin = composer.compose_morning(config)
        assert checkin.wearable_observations == []
