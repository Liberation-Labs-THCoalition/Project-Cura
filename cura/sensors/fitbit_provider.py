"""Fitbit integration — Tier 1 wearable provider.

pip install python-fitbit

Most elders who own a wearable own a Fitbit. This provider uses the
official Fitbit Web API (OAuth2) to pull heart rate, steps, sleep,
and SpO2 data.

Setup:
  1. Register an app at dev.fitbit.com (Personal type, free)
  2. Get client_id and client_secret
  3. Run the OAuth2 flow once to get access/refresh tokens
  4. Cura polls every 15 minutes from there

Rate limit: 150 requests/hour — plenty for eldercare polling.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from cura.sensors.wearable import WearableProvider, WearableReading

logger = logging.getLogger(__name__)


class FitbitProvider(WearableProvider):
    """Pull health data from Fitbit's Web API.

    Args:
        client_id: Fitbit API client ID
        client_secret: Fitbit API client secret
        access_token: OAuth2 access token
        refresh_token: OAuth2 refresh token
    """

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        access_token: str = "",
        refresh_token: str = "",
        dry_run: bool = False,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._dry_run = dry_run
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        if self._dry_run:
            return None

        try:
            import fitbit
            self._client = fitbit.Fitbit(
                self._client_id,
                self._client_secret,
                access_token=self._access_token,
                refresh_token=self._refresh_token,
                refresh_cb=self._on_token_refresh,
            )
            return self._client
        except ImportError:
            logger.warning("python-fitbit not installed — pip install python-fitbit")
            self._dry_run = True
            return None

    def _on_token_refresh(self, token: dict) -> None:
        self._access_token = token.get("access_token", "")
        self._refresh_token = token.get("refresh_token", "")
        logger.info("Fitbit token refreshed")

    async def fetch_latest(self) -> WearableReading | None:
        """Fetch current heart rate from Fitbit."""
        now = datetime.now(timezone.utc)

        if self._dry_run:
            return WearableReading(
                timestamp=now, source="fitbit",
                heart_rate=72, resting_heart_rate=68,
            )

        client = self._get_client()
        if not client:
            return None

        try:
            hr_data = client.intraday_time_series(
                "activities/heart",
                detail_level="1min",
            )
            dataset = (
                hr_data
                .get("activities-heart-intraday", {})
                .get("dataset", [])
            )
            latest_hr = dataset[-1]["value"] if dataset else None

            resting = (
                hr_data
                .get("activities-heart", [{}])[0]
                .get("value", {})
                .get("restingHeartRate")
            )

            return WearableReading(
                timestamp=now, source="fitbit",
                heart_rate=latest_hr,
                resting_heart_rate=resting,
            )
        except Exception as e:
            logger.error("Fitbit HR fetch failed: %s", e)
            return None

    async def fetch_daily_summary(self, date: datetime | None = None) -> WearableReading | None:
        """Fetch daily summary: steps, sleep, heart rate, SpO2."""
        now = datetime.now(timezone.utc)
        date_str = (date or now).strftime("%Y-%m-%d")

        if self._dry_run:
            return WearableReading(
                timestamp=now, source="fitbit",
                heart_rate=72, resting_heart_rate=68,
                steps=4200, active_minutes=35, calories=1850,
                sleep_minutes=410, sleep_quality="fair",
                sleep_deep_minutes=85, sleep_rem_minutes=62,
                spo2=96.5,
            )

        client = self._get_client()
        if not client:
            return None

        reading = WearableReading(timestamp=now, source="fitbit")

        try:
            activity = client.activities(date=date_str)
            summary = activity.get("summary", {})
            reading.steps = summary.get("steps")
            reading.active_minutes = (
                summary.get("fairlyActiveMinutes", 0)
                + summary.get("veryActiveMinutes", 0)
            )
            reading.calories = summary.get("caloriesOut")
        except Exception as e:
            logger.warning("Fitbit activity fetch failed: %s", e)

        try:
            sleep = client.sleep(date=date_str)
            sleep_data = sleep.get("summary", {})
            reading.sleep_minutes = sleep_data.get("totalMinutesAsleep")
            reading.time_in_bed_minutes = sleep_data.get("totalTimeInBed")

            stages = sleep_data.get("stages", {})
            reading.sleep_deep_minutes = stages.get("deep")
            reading.sleep_rem_minutes = stages.get("rem")

            if reading.sleep_minutes:
                if reading.sleep_minutes >= 420:
                    reading.sleep_quality = "good"
                elif reading.sleep_minutes >= 300:
                    reading.sleep_quality = "fair"
                else:
                    reading.sleep_quality = "poor"
        except Exception as e:
            logger.warning("Fitbit sleep fetch failed: %s", e)

        try:
            hr_data = client.intraday_time_series("activities/heart")
            hr_summary = hr_data.get("activities-heart", [{}])[0].get("value", {})
            reading.resting_heart_rate = hr_summary.get("restingHeartRate")
        except Exception as e:
            logger.warning("Fitbit HR fetch failed: %s", e)

        try:
            spo2 = client.intraday_time_series("spo2")
            spo2_value = spo2.get("value", spo2.get("avg"))
            if isinstance(spo2_value, (int, float)):
                reading.spo2 = float(spo2_value)
        except Exception as e:
            logger.warning("Fitbit SpO2 fetch failed: %s", e)

        return reading
