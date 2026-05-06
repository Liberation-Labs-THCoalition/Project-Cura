"""Wearable integration — turning body data into care decisions.

A chatbot asks "how are you?"
Cura already knows your heart rate was elevated at 3am
and asks if you slept okay.

Three tiers:
  Tier 1: Fitbit Web API (most elders already have one)
  Tier 2: Gadgetbridge relay (Amazfit/Xiaomi, $30 bands)
  Tier 3: Medical BLE devices (pulse oximeter, BP cuff)

All tiers produce the same WearableReading — the rest of the
system doesn't care where the data came from.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WearableReading:
    """A single snapshot of wearable sensor data.

    Not all fields will be populated — depends on the device.
    """
    timestamp: datetime
    source: str  # "fitbit", "gadgetbridge", "ble_oximeter", etc.

    # Vitals
    heart_rate: int | None = None
    resting_heart_rate: int | None = None
    spo2: float | None = None  # 0-100%
    blood_pressure_systolic: int | None = None
    blood_pressure_diastolic: int | None = None

    # Activity
    steps: int | None = None
    active_minutes: int | None = None
    calories: int | None = None

    # Sleep
    sleep_minutes: int | None = None
    sleep_quality: str | None = None  # "good", "fair", "poor"
    sleep_deep_minutes: int | None = None
    sleep_rem_minutes: int | None = None
    time_in_bed_minutes: int | None = None

    # Alerts
    fall_detected: bool = False
    sos_pressed: bool = False


@dataclass
class HealthBaseline:
    """Learned baseline for an elder's typical readings.

    Built over the first 2 weeks, then continuously updated.
    Deviations from baseline trigger concern.
    """
    avg_resting_hr: float = 70.0
    avg_steps_per_day: float = 3000.0
    avg_sleep_minutes: float = 420.0  # 7 hours
    avg_spo2: float = 96.0
    typical_wake_time: int = 7  # hour
    typical_sleep_time: int = 22

    hr_stddev: float = 8.0
    steps_stddev: float = 1000.0
    sleep_stddev: float = 60.0


class WearableAnalyzer:
    """Analyze wearable readings against baseline for health concerns.

    Produces plain-language observations, not diagnoses.
    """

    def __init__(self, baseline: HealthBaseline | None = None) -> None:
        self.baseline = baseline or HealthBaseline()
        self._readings: list[WearableReading] = []

    def add_reading(self, reading: WearableReading) -> None:
        self._readings.append(reading)

    def analyze_latest(self) -> list[str]:
        """Analyze the most recent reading against baseline.

        Returns a list of plain-language observations for the
        check-in composer to weave into conversation.
        """
        if not self._readings:
            return []

        r = self._readings[-1]
        observations = []

        if r.fall_detected:
            observations.append("FALL DETECTED — triggering crisis protocol")

        if r.sos_pressed:
            observations.append("SOS button pressed — triggering crisis protocol")

        if r.heart_rate is not None:
            if r.heart_rate > self.baseline.avg_resting_hr + 2 * self.baseline.hr_stddev:
                observations.append(
                    f"Your heart rate has been higher than usual — {r.heart_rate} bpm. "
                    "How are you feeling? Any chest discomfort?"
                )
            elif r.heart_rate < self.baseline.avg_resting_hr - 2 * self.baseline.hr_stddev:
                observations.append(
                    f"Your heart rate is a bit low — {r.heart_rate} bpm. "
                    "Are you feeling dizzy or lightheaded?"
                )

        if r.spo2 is not None and r.spo2 < 92:
            observations.append(
                f"Your oxygen level is reading {r.spo2}%. That's lower than usual. "
                "Are you having any trouble breathing?"
            )

        if r.sleep_minutes is not None:
            if r.sleep_minutes < self.baseline.avg_sleep_minutes - self.baseline.sleep_stddev:
                hours = r.sleep_minutes / 60
                observations.append(
                    f"It looks like you only got about {hours:.1f} hours of sleep last night. "
                    "Are you feeling tired today?"
                )

        if r.steps is not None:
            yesterday_steps = self._get_yesterday_steps()
            if yesterday_steps is not None:
                if yesterday_steps < self.baseline.avg_steps_per_day * 0.3:
                    observations.append(
                        f"You were less active than usual yesterday — {yesterday_steps} steps. "
                        "Everything okay? Even a short walk helps."
                    )

        return observations

    def check_inactivity(self, hours: int = 12) -> bool:
        """Check if there's been no movement data for a concerning period."""
        if not self._readings:
            return False
        latest = self._readings[-1]
        age = datetime.now(timezone.utc) - latest.timestamp
        return age > timedelta(hours=hours)

    def update_baseline(self) -> None:
        """Update baseline from the last 14 days of readings."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        recent = [r for r in self._readings if r.timestamp >= cutoff]
        if len(recent) < 7:
            return

        hr_values = [r.resting_heart_rate or r.heart_rate for r in recent if r.heart_rate]
        if hr_values:
            self.baseline.avg_resting_hr = sum(hr_values) / len(hr_values)
            mean = self.baseline.avg_resting_hr
            self.baseline.hr_stddev = (sum((v - mean) ** 2 for v in hr_values) / len(hr_values)) ** 0.5

        step_values = [r.steps for r in recent if r.steps is not None]
        if step_values:
            self.baseline.avg_steps_per_day = sum(step_values) / len(step_values)

        sleep_values = [r.sleep_minutes for r in recent if r.sleep_minutes is not None]
        if sleep_values:
            self.baseline.avg_sleep_minutes = sum(sleep_values) / len(sleep_values)
            mean = self.baseline.avg_sleep_minutes
            self.baseline.sleep_stddev = (sum((v - mean) ** 2 for v in sleep_values) / len(sleep_values)) ** 0.5

        spo2_values = [r.spo2 for r in recent if r.spo2 is not None]
        if spo2_values:
            self.baseline.avg_spo2 = sum(spo2_values) / len(spo2_values)

    def _get_yesterday_steps(self) -> int | None:
        yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
        for r in reversed(self._readings):
            if r.timestamp.date() == yesterday and r.steps is not None:
                return r.steps
        return None

    @property
    def crisis_detected(self) -> bool:
        if not self._readings:
            return False
        r = self._readings[-1]
        return r.fall_detected or r.sos_pressed

    @property
    def readings(self) -> list[WearableReading]:
        return list(self._readings)


class WearableProvider(ABC):
    """Base class for wearable data providers."""

    @abstractmethod
    async def fetch_latest(self) -> WearableReading | None:
        """Fetch the most recent reading from the device/service."""

    @abstractmethod
    async def fetch_daily_summary(self, date: datetime | None = None) -> WearableReading | None:
        """Fetch a daily summary (steps, sleep, avg HR)."""
