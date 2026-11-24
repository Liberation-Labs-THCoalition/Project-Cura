"""Under a daemon, `cura run` and `cura webhook` start from what `cura setup` wrote, with no flags (2026-11-24).

Nexus's read of deploy/macos/run.sh found that `cura run` required --config, so the daemon's plain `cura run` would
have failed at argument parsing and restarted forever. And the webhook greeted everyone as "friend" unless
--elder-name was passed, which a support account cannot add to a root-owned daemon.
"""
from __future__ import annotations

import json
import sys

import pytest

import cura.__main__ as cura_main
import cura.comms.webhook as webhook


@pytest.fixture
def one_setup():
    """The isolated home (conftest's autouse fixture) where `cura setup` wrote exactly one config."""
    from pathlib import Path
    cura_dir = Path.home() / ".cura"
    cfg = cura_dir / "elder.json"
    cfg.write_text(json.dumps({"name": "Pat Example", "preferred_name": "Pat"}))
    (cura_dir / "setup-progress.json").write_text(json.dumps({"config_path": str(cfg)}))
    return cfg


def test_cura_run_without_config_uses_the_one_setup_wrote(monkeypatch, one_setup):
    seen = {}
    monkeypatch.setattr(cura_main, "_run_scheduled", lambda path, dry_run=False: seen.setdefault("path", path))
    monkeypatch.setattr(sys, "argv", ["cura", "run"])
    cura_main.main()
    assert seen.get("path") == str(one_setup)


def test_cura_run_with_no_setup_explains_and_exits(monkeypatch, capsys):
    # conftest's isolated home has an empty ~/.cura: nothing set up
    monkeypatch.setattr(cura_main, "_run_scheduled", lambda *a, **k: pytest.fail("ran with no config"))
    monkeypatch.setattr(sys, "argv", ["cura", "run"])
    with pytest.raises(SystemExit) as e:
        cura_main.main()
    assert e.value.code == 1
    assert "cura setup" in capsys.readouterr().out


class _FakeApp:
    def run(self, **kw):
        pass


def _start_webhook(monkeypatch, *extra):
    got = {}
    monkeypatch.setattr(cura_main, "_build_responder", lambda path: object())
    monkeypatch.setattr(cura_main, "_twilio_settings", lambda path: ({"auth_token": "test-token"}, "https://example.test"))

    def fake_create_app(**kw):
        got.update(kw)
        return _FakeApp()
    monkeypatch.setattr(webhook, "create_app", fake_create_app)
    monkeypatch.setattr(sys, "argv", ["cura", "webhook", *extra])
    cura_main.main()
    return got


def test_webhook_greets_by_the_configured_name_when_none_is_given(monkeypatch, one_setup):
    assert _start_webhook(monkeypatch)["elder_name"] == "Pat"


def test_an_explicit_elder_name_still_wins(monkeypatch, one_setup):
    assert _start_webhook(monkeypatch, "--elder-name", "Sam")["elder_name"] == "Sam"
