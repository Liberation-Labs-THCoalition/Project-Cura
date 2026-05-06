"""Tests for console — Cura's interactive terminal mode."""
from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from cura.pulse.eldercare_pulse import ElderProfile, EldercarePulseConfig
from cura.console import run_demo


def _make_config() -> EldercarePulseConfig:
    return EldercarePulseConfig(ElderProfile(
        name="Margaret", preferred_name="Margaret",
        phone="", medications=[{"name": "Lisinopril", "time": "morning"}],
        emergency_contacts=[], primary_caregiver={},
    ))


class TestDemo:
    def test_demo_runs_without_error(self, capsys):
        config = _make_config()
        run_demo(config, weather={"temp_f": 88})
        output = capsys.readouterr().out
        assert "Margaret" in output
        assert "Lisinopril" in output
        assert "medications confirmed" in output.lower()

    def test_demo_with_hot_weather(self, capsys):
        config = _make_config()
        run_demo(config, weather={"temp_f": 100})
        output = capsys.readouterr().out
        assert "100°" in output or "water" in output.lower()


class TestEntryPoint:
    def test_main_no_args_prints_help(self, capsys):
        from cura.__main__ import main
        import sys
        old_argv = sys.argv
        sys.argv = ["cura"]
        main()
        sys.argv = old_argv
        output = capsys.readouterr().out
        assert "Quick start" in output
