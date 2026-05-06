"""Gadgetbridge integration — Tier 2 wearable provider.

Gadgetbridge is an open source Android app that communicates with
50+ wearable devices (Xiaomi Mi Band, Amazfit, PineTime, Fossil, etc.)
via BLE. It stores all data in a local SQLite database.

This provider reads from Gadgetbridge's exported database or from
a synced copy of the DB. No proprietary APIs, no cloud dependency.

Setup:
  1. Install Gadgetbridge on a cheap Android phone
  2. Pair the wearable (Amazfit Band 5 recommended, ~$30)
  3. Enable DB export in Gadgetbridge settings
  4. Sync the DB file to the machine running Cura
     (via USB, rsync, Syncthing, or adb pull)

Supported devices (via Gadgetbridge):
  - Xiaomi Mi Band 3/4/5/6/7/8
  - Amazfit Band 5/7, Bip, GTS, GTR
  - PineTime
  - Fossil/Skagen Hybrid HR
  - Casio, Garmin (partial), and many more
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cura.sensors.wearable import WearableProvider, WearableReading

logger = logging.getLogger(__name__)


class GadgetbridgeProvider(WearableProvider):
    """Read wearable data from Gadgetbridge's SQLite database.

    Args:
        db_path: Path to the Gadgetbridge export DB
        device_id: Device ID in Gadgetbridge (usually 1 for single device)
    """

    def __init__(
        self,
        db_path: str = "",
        device_id: int = 1,
        dry_run: bool = False,
    ) -> None:
        self._db_path = Path(db_path) if db_path else None
        self._device_id = device_id
        self._dry_run = dry_run

    def _connect(self) -> sqlite3.Connection | None:
        if self._dry_run or not self._db_path:
            return None
        if not self._db_path.exists():
            logger.warning("Gadgetbridge DB not found: %s", self._db_path)
            return None
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    async def fetch_latest(self) -> WearableReading | None:
        now = datetime.now(timezone.utc)

        if self._dry_run:
            return WearableReading(
                timestamp=now, source="gadgetbridge",
                heart_rate=74, steps=1200,
            )

        conn = self._connect()
        if not conn:
            return None

        try:
            reading = WearableReading(timestamp=now, source="gadgetbridge")

            # Heart rate — most recent sample
            row = conn.execute(
                "SELECT HEART_RATE, TIMESTAMP FROM MI_BAND_ACTIVITY_SAMPLE "
                "WHERE DEVICE_ID = ? AND HEART_RATE > 0 AND HEART_RATE < 255 "
                "ORDER BY TIMESTAMP DESC LIMIT 1",
                (self._device_id,),
            ).fetchone()
            if row:
                reading.heart_rate = row["HEART_RATE"]
                reading.timestamp = datetime.fromtimestamp(row["TIMESTAMP"], tz=timezone.utc)

            # Steps — today's total
            today_start = int(datetime.combine(
                now.date(), datetime.min.time(),
            ).replace(tzinfo=timezone.utc).timestamp())
            row = conn.execute(
                "SELECT SUM(STEPS) as total_steps FROM MI_BAND_ACTIVITY_SAMPLE "
                "WHERE DEVICE_ID = ? AND TIMESTAMP >= ? AND STEPS > 0",
                (self._device_id, today_start),
            ).fetchone()
            if row and row["total_steps"]:
                reading.steps = row["total_steps"]

            return reading
        except Exception as e:
            logger.error("Gadgetbridge read failed: %s", e)
            return None
        finally:
            conn.close()

    async def fetch_daily_summary(self, date: datetime | None = None) -> WearableReading | None:
        now = datetime.now(timezone.utc)
        target_date = (date or now).date()

        if self._dry_run:
            return WearableReading(
                timestamp=now, source="gadgetbridge",
                heart_rate=74, resting_heart_rate=66,
                steps=3800, sleep_minutes=390,
                sleep_quality="fair", spo2=95.0,
            )

        conn = self._connect()
        if not conn:
            return None

        try:
            reading = WearableReading(timestamp=now, source="gadgetbridge")

            day_start = int(datetime.combine(
                target_date, datetime.min.time(),
            ).replace(tzinfo=timezone.utc).timestamp())
            day_end = day_start + 86400

            # Steps
            row = conn.execute(
                "SELECT SUM(STEPS) as total FROM MI_BAND_ACTIVITY_SAMPLE "
                "WHERE DEVICE_ID = ? AND TIMESTAMP >= ? AND TIMESTAMP < ? AND STEPS > 0",
                (self._device_id, day_start, day_end),
            ).fetchone()
            if row and row["total"]:
                reading.steps = row["total"]

            # Heart rate — average and resting (min of reasonable values)
            rows = conn.execute(
                "SELECT HEART_RATE FROM MI_BAND_ACTIVITY_SAMPLE "
                "WHERE DEVICE_ID = ? AND TIMESTAMP >= ? AND TIMESTAMP < ? "
                "AND HEART_RATE > 30 AND HEART_RATE < 220",
                (self._device_id, day_start, day_end),
            ).fetchall()
            if rows:
                hrs = [r["HEART_RATE"] for r in rows]
                reading.heart_rate = round(sum(hrs) / len(hrs))
                reading.resting_heart_rate = min(hrs)

            # Sleep — Gadgetbridge uses RAW_KIND values
            # KIND=1 = light sleep, KIND=2 = deep sleep, KIND=5 = REM (device-dependent)
            night_start = day_start - 8 * 3600  # look back 8h for previous night
            sleep_rows = conn.execute(
                "SELECT RAW_KIND, COUNT(*) as minutes FROM MI_BAND_ACTIVITY_SAMPLE "
                "WHERE DEVICE_ID = ? AND TIMESTAMP >= ? AND TIMESTAMP < ? "
                "AND RAW_KIND IN (1, 2, 5)",
                (self._device_id, night_start, day_start),
            ).fetchall()
            total_sleep = 0
            for sr in sleep_rows:
                total_sleep += sr["minutes"]
                if sr["RAW_KIND"] == 2:
                    reading.sleep_deep_minutes = sr["minutes"]
                elif sr["RAW_KIND"] == 5:
                    reading.sleep_rem_minutes = sr["minutes"]
            if total_sleep > 0:
                reading.sleep_minutes = total_sleep
                if total_sleep >= 420:
                    reading.sleep_quality = "good"
                elif total_sleep >= 300:
                    reading.sleep_quality = "fair"
                else:
                    reading.sleep_quality = "poor"

            # SpO2 — if device supports it
            try:
                spo2_row = conn.execute(
                    "SELECT TYPE_NUM FROM MI_BAND_ACTIVITY_SAMPLE "
                    "WHERE DEVICE_ID = ? AND TIMESTAMP >= ? AND TIMESTAMP < ? "
                    "AND RAW_KIND = 90 ORDER BY TIMESTAMP DESC LIMIT 1",
                    (self._device_id, day_start, day_end),
                ).fetchone()
                if spo2_row:
                    reading.spo2 = float(spo2_row["TYPE_NUM"])
            except Exception:
                pass

            return reading
        except Exception as e:
            logger.error("Gadgetbridge daily summary failed: %s", e)
            return None
        finally:
            conn.close()
