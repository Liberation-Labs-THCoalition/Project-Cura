"""`cura webhook` listens on this machine only, unless told otherwise (2026-11-23).

Cura reaches Twilio through a tunnel on the same machine. Binding 0.0.0.0 opened
the port to every device on the household's network, and on a Mac it made the
firewall ask the household whether to accept incoming connections.
"""
from __future__ import annotations

import sys

import pytest

import cura.__main__ as cura_main
import cura.comms.webhook as webhook


class _FakeApp:
    def __init__(self):
        self.ran_with = None

    def run(self, **kw):
        self.ran_with = kw


@pytest.fixture
def started(monkeypatch, tmp_path):
    cfg = tmp_path / "cura.json"
    cfg.write_text("{}")
    app = _FakeApp()
    monkeypatch.setattr(cura_main, "_build_responder", lambda path: object())
    monkeypatch.setattr(cura_main, "_twilio_settings",
                        lambda path: ({"auth_token": "test-token"}, "https://example.test"))
    monkeypatch.setattr(webhook, "create_app", lambda **kw: app)

    def start(*extra):
        monkeypatch.setattr(sys, "argv", ["cura", "webhook", "--config", str(cfg), *extra])
        cura_main.main()
        return app.ran_with
    return start


def test_the_webhook_listens_on_this_machine_by_default(started):
    ran = started()
    assert ran is not None, "the server was never started"
    assert ran["host"] == "127.0.0.1"
    assert ran["port"] == 5000


def test_another_address_is_still_possible_when_asked(started):
    ran = started("--host", "0.0.0.0", "--port", "5050")
    assert ran["host"] == "0.0.0.0"
    assert ran["port"] == 5050
