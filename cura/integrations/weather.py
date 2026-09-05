"""Weather from the National Weather Service, or nothing at all.

Weather never reached a real call. Both production sites called
compose_morning(pulse_config) with no weather argument and nothing anywhere
fetched any, so the enrichment that says "it's going to be eight degrees today,
please stay indoors" -- and the ALERT path with it -- had no supply. In rural
Wyoming that is a safety line, not a nicety.

WHY NWS AND NOT A WEATHER API. api.weather.gov is free, requires no key, no
signup and no account, and it is the authoritative source that commercial
services resample. More importantly it carries OFFICIAL WATCHES AND WARNINGS,
which is the part that matters: a thermometer on the household's own security
panel can tell you it is eight degrees, and "it is eight degrees" changes
nobody's behaviour. "Winter Storm Warning until 6pm" does.

THE RULE, which is the same one everything else here runs on:

    A FAILED FETCH SAYS NOTHING.

If NWS is unreachable, Cura does not mention the weather. It does not guess, and
it does not serve yesterday's warning as today's. Stale weather stated
confidently is the same defect as a dead sensor naming a room -- and worse here,
because a lapsed warning tells someone it is safe to go out.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

#: NWS asks for a contact in the User-Agent. Not enforced, but requested, and
#: sending one costs nothing.
USER_AGENT = "(Cura eldercare companion, cc@liberation-labs.org)"

#: How long a fetch stays usable. Short, because the point of the alert path is
#: that it is CURRENT. A warning that expired an hour ago is worse than silence.
FRESH_FOR = timedelta(minutes=90)

TIMEOUT = 10


@dataclass(frozen=True)
class Weather:
    """What Cura may say. `fetched_at` is load-bearing, not metadata."""
    temp_f: int | None
    condition: str
    alerts: tuple[str, ...]
    fetched_at: datetime

    def stale(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return (now - self.fetched_at) > FRESH_FOR

    def as_enrichment_input(self, now: datetime | None = None) -> dict | None:
        """The dict the composer expects, or None when it must not be used.

        Returns None when stale rather than returning old data with a flag,
        because a flag has to be checked and a None cannot be forgotten.
        """
        if self.stale(now):
            return None
        out: dict = {"alerts": list(self.alerts)}
        if self.temp_f is not None:
            out["temp_f"] = self.temp_f
        if self.condition:
            out["condition"] = self.condition
        return out


def _get(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/geo+json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        logger.info("weather fetch failed (%s) — Cura will not mention it", e)
        return None


def fetch(lat: float, lon: float, *, now: datetime | None = None) -> Weather | None:
    """Current conditions and active alerts, or None.

    None is the honest answer for every failure: unreachable, malformed,
    rate-limited, or a location NWS does not cover. Every caller must treat None
    as "say nothing about the weather", which is why this returns None rather
    than an empty Weather -- an empty Weather would be spoken as "no warnings",
    and we do not know that.
    """
    now = now or datetime.now(timezone.utc)
    points = _get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")
    if not points:
        return None
    props = points.get("properties", {})

    temp_f, condition = None, ""
    forecast = _get(props.get("forecast", "")) if props.get("forecast") else None
    if forecast:
        periods = forecast.get("properties", {}).get("periods", [])
        if periods:
            p = periods[0]
            if p.get("temperatureUnit") == "F" and isinstance(p.get("temperature"), int):
                temp_f = p["temperature"]
            condition = (p.get("shortForecast") or "").strip()

    # Alerts come from the ZONE, not the point. A point query can miss a warning
    # that covers the county the household is actually in.
    alerts: list[str] = []
    zone = props.get("county") or props.get("forecastZone") or ""
    if zone:
        data = _get(f"https://api.weather.gov/alerts/active?zone={zone.rsplit('/', 1)[-1]}")
        for f in (data or {}).get("features", []):
            head = (f.get("properties", {}).get("headline") or "").strip()
            if head:
                alerts.append(head)

    if temp_f is None and not condition and not alerts:
        # Reached NWS and learned nothing usable. Not the same as "no warnings".
        return None
    return Weather(temp_f=temp_f, condition=condition,
                   alerts=tuple(alerts), fetched_at=now)


def geocode(address: str) -> tuple[float, float] | None:
    """Street address to coordinates, via the US Census geocoder.

    Free, keyless, US-only, and it is the one piece of this that the household
    should never be asked for. Nobody knows their own latitude, and asking a man
    with failing eyesight to find it would be its own small cruelty.

    Returns None on any failure or ambiguity. A WRONG coordinate is worse than
    none: it would produce confident weather for somewhere else, and a warning
    for the wrong county is the same class of error as a stale sensor naming a
    room. One exact match or nothing.
    """
    import urllib.parse
    if not (address or "").strip():
        return None
    q = urllib.parse.urlencode({
        "address": address.strip(),
        "benchmark": "Public_AR_Current",
        "format": "json",
    })
    data = _get(f"https://geocoding.geo.census.gov/geocoder/locations/"
                f"onelineaddress?{q}")
    matches = (data or {}).get("result", {}).get("addressMatches", [])
    if len(matches) != 1:
        logger.info("geocode of %r gave %d matches — refusing to guess",
                    address, len(matches))
        return None
    c = matches[0].get("coordinates", {})
    try:
        return float(c["y"]), float(c["x"])
    except (KeyError, TypeError, ValueError):
        return None


def for_household(config: dict, *, now: datetime | None = None) -> dict | None:
    """The weather dict for a check-in, or None to say nothing.

    Coordinates are cached into the config the first time, so the geocoder is
    called once per household rather than twice a day forever.
    """
    lat, lon = config.get("lat"), config.get("lon")
    if lat is None or lon is None:
        found = geocode(config.get("address", ""))
        if not found:
            return None
        lat, lon = found
        config["lat"], config["lon"] = lat, lon
    w = fetch(lat, lon, now=now)
    return w.as_enrichment_input(now) if w else None
