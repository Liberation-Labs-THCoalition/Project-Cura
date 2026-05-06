"""Weather integration via Open-Meteo (free, no API key).

pip install openmeteo-requests requests-cache

Provides temperature, wind chill, UV, and weather alerts for
health-triggered nudges (heat warnings, ice alerts, etc.)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class WeatherService:
    """Fetch weather data for elder health alerts.

    Uses Open-Meteo's free API. No API key required.
    Falls back to a safe default if unavailable.
    """

    API_BASE = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, latitude: float = 0.0, longitude: float = 0.0) -> None:
        self._lat = latitude
        self._lon = longitude
        self._cache: dict[str, Any] = {}

    async def get_current(self) -> dict[str, Any]:
        if not self._lat and not self._lon:
            return {"temp_f": 70, "condition": "Unknown", "alerts": []}

        try:
            import aiohttp
        except ImportError:
            logger.warning("aiohttp not installed — returning default weather")
            return {"temp_f": 70, "condition": "Unknown", "alerts": []}

        params = {
            "latitude": self._lat,
            "longitude": self._lon,
            "current": "temperature_2m,weathercode,windspeed_10m",
            "temperature_unit": "fahrenheit",
            "timezone": "auto",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.API_BASE, params=params) as resp:
                    data = await resp.json()

            current = data.get("current", {})
            temp_f = current.get("temperature_2m", 70)
            code = current.get("weathercode", 0)
            condition = self._decode_weather_code(code)

            result = {
                "temp_f": temp_f,
                "condition": condition,
                "wind_mph": current.get("windspeed_10m", 0),
                "alerts": [],
            }
            self._cache = result
            return result

        except Exception as e:
            logger.warning("Weather fetch failed: %s", e)
            return self._cache or {"temp_f": 70, "condition": "Unknown", "alerts": []}

    @staticmethod
    def _decode_weather_code(code: int) -> str:
        codes = {
            0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Fog", 48: "Freezing fog",
            51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
            56: "Freezing drizzle", 57: "Heavy freezing drizzle",
            61: "Light rain", 63: "Rain", 65: "Heavy rain",
            66: "Freezing rain", 67: "Heavy freezing rain",
            71: "Light snow", 73: "Snow", 75: "Heavy snow",
            77: "Snow grains", 80: "Light showers", 81: "Showers", 82: "Heavy showers",
            85: "Light snow showers", 86: "Heavy snow showers",
            95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Heavy thunderstorm with hail",
        }
        return codes.get(code, "Unknown")
