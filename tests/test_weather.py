"""Weather from NWS, or nothing at all.

Weather never reached a real call: both production sites passed no weather
argument and nothing anywhere fetched any, so the enrichment that says "it's
going to be eight degrees today, please stay indoors" — and the ALERT path with
it — had no supply. In rural Wyoming that is a safety line.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cura.integrations import weather as W

NOW = datetime(2026, 9, 4, 18, 0, tzinfo=timezone.utc)


def _w(**kw):
    base = dict(temp_f=8, condition="Snow", alerts=("Winter Storm Warning",),
                fetched_at=NOW)
    base.update(kw)
    return W.Weather(**base)


class TestAFailedFetchSaysNothing:
    """It does not guess, and it does not serve yesterday's warning as today's.
    A lapsed warning tells someone it is safe to go out."""

    def test_an_unreachable_service_returns_none(self, monkeypatch):
        monkeypatch.setattr(W, "_get", lambda url: None)
        assert W.fetch(44.35, -106.70, now=NOW) is None

    def test_reaching_nws_and_learning_nothing_is_also_none(self, monkeypatch):
        """Not the same as "no warnings". An empty Weather would be spoken as
        a clean bill of health we did not actually get."""
        monkeypatch.setattr(W, "_get", lambda url: {"properties": {}})
        assert W.fetch(44.35, -106.70, now=NOW) is None

    def test_no_address_means_no_weather(self):
        assert W.for_household({"address": ""}) is None


class TestStaleWeatherIsNotServed:
    def test_fresh_weather_is_usable(self):
        assert _w().as_enrichment_input(NOW + timedelta(minutes=30)) is not None

    def test_stale_weather_returns_none_not_old_data(self):
        """None cannot be forgotten; a staleness flag has to be checked."""
        assert _w().as_enrichment_input(NOW + timedelta(hours=4)) is None

    def test_the_boundary_is_ninety_minutes(self):
        assert _w().stale(NOW + timedelta(minutes=89)) is False
        assert _w().stale(NOW + timedelta(minutes=91)) is True

    def test_an_expired_warning_is_never_spoken(self):
        """The specific harm: a lapsed Winter Storm Warning told to someone
        deciding whether to go outside."""
        old = _w(fetched_at=NOW - timedelta(hours=6))
        assert old.as_enrichment_input(NOW) is None


class TestTheAlertPathIsWhatMatters:
    def test_an_alert_reaches_the_enrichment(self):
        from cura.pulse.daily_enrichments import WeatherAlert
        out = _w().as_enrichment_input(NOW)
        e = WeatherAlert().get(out)
        assert e is not None
        assert "Winter Storm Warning" in e.message

    def test_conditions_alone_still_work_without_an_alert(self):
        out = _w(alerts=()).as_enrichment_input(NOW)
        assert out["alerts"] == [] and out["temp_f"] == 8

    def test_missing_temperature_is_omitted_not_defaulted(self):
        """The enrichment defaults an absent temp to 70F. Sending a key we do
        not have would make it say "it'll be 70 degrees" in a blizzard."""
        out = _w(temp_f=None).as_enrichment_input(NOW)
        assert "temp_f" not in out


class TestGeocodingRefusesToGuess:
    def test_an_ambiguous_address_returns_none(self, monkeypatch):
        """A wrong coordinate produces confident weather for somewhere else,
        and a warning for the wrong county."""
        monkeypatch.setattr(W, "_get", lambda url: {"result": {"addressMatches": [
            {"coordinates": {"y": 1, "x": 2}}, {"coordinates": {"y": 3, "x": 4}}]}})
        assert W.geocode("ambiguous") is None

    def test_no_match_returns_none(self, monkeypatch):
        monkeypatch.setattr(W, "_get", lambda url: {"result": {"addressMatches": []}})
        assert W.geocode("nowhere") is None

    def test_exactly_one_match_is_used(self, monkeypatch):
        monkeypatch.setattr(W, "_get", lambda url: {"result": {"addressMatches": [
            {"coordinates": {"y": 44.3477, "x": -106.6989}}]}})
        assert W.geocode("41 N Main St, Buffalo WY") == (44.3477, -106.6989)

    def test_coordinates_are_cached_so_we_geocode_once(self, monkeypatch):
        calls = []
        monkeypatch.setattr(W, "geocode", lambda a: (calls.append(a), (1.0, 2.0))[1])
        monkeypatch.setattr(W, "fetch", lambda lat, lon, now=None: _w())
        cfg = {"address": "somewhere"}
        W.for_household(cfg); W.for_household(cfg)
        assert len(calls) == 1
        assert cfg["lat"] == 1.0 and cfg["lon"] == 2.0


class TestItIsActuallyWired:
    def test_the_morning_check_in_is_given_weather(self):
        """Both production sites passed no weather argument at all."""
        import ast
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent
               / "cura/__main__.py").read_text()
        tree = ast.parse(src)
        calls = [c for c in ast.walk(tree) if isinstance(c, ast.Call)
                 and isinstance(c.func, ast.Attribute)
                 and c.func.attr == "compose_morning"]
        assert calls, "no compose_morning call found"
        for c in calls:
            assert any(k.arg == "weather" for k in c.keywords), \
                ("a compose_morning call site gets no weather — including the "
                 "rehearse path, which must show what will actually be heard")
