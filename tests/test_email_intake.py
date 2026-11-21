"""Email is included and scanned (Thomas, 2026-11-17), first local step.

Thomas: "Let's also make sure email is included and scanned, it's the most
common attack surface for seniors." docs/EMAIL_SCOPE_PLAN.md is the plan; E1 is
what these test: one real message, read from its raw RFC 822 form, through the
real entry points (`cura scan-email` via cura.__main__, and the MCP server's
cura_scam_check through its own call_tool handler). The scanner existed with no
caller and its own words promised "Cura will alert your caregiver".

Three guarantees:
  1. A real phishing message's tricks are seen: a link that shows medicare.gov
     and goes elsewhere, a "Medicare" name on someone else's address, her mail
     server's SPF/DMARC failure, replies redirected to another domain.
  2. The body is read and dropped: a sentinel in it appears in no output.
  3. Nothing says anyone was told, because nobody is.
"""
from __future__ import annotations

import json
import sys
from email.message import EmailMessage

import pytest

from tests.test_no_false_alert import _payload_claims_alert, _text_claims_alert
from tests.test_no_false_alert import mcp_call, sent  # noqa: F401  (fixtures)

#: Planted in each body. It must never come back out.
SENTINEL = "PLUM-CANARY-7741"


def _phish() -> bytes:
    m = EmailMessage()
    m["From"] = '"Medicare Benefits" <claims@medicare-help.xyz>'
    m["To"] = "margaret@example.org"
    m["Subject"] = "Your benefits are on hold"
    m["Reply-To"] = "refund.desk@example.net"
    m["Return-Path"] = "<bounce@mailer.example.net>"
    m["Authentication-Results"] = ("mx.example.org; spf=fail smtp.mailfrom=medicare-help.xyz; "
                                   "dkim=none; dmarc=fail header.from=medicare-help.xyz")
    m.set_content(f"Please confirm your card details. {SENTINEL}")
    m.add_alternative(
        f"<p>Please confirm your card details. {SENTINEL}</p>"
        '<p><a href="http://203.0.113.9/login">https://www.medicare.gov/account</a></p>',
        subtype="html")
    return bytes(m)


def _legit() -> bytes:
    m = EmailMessage()
    m["From"] = '"Medicare.gov" <noreply@medicare.gov>'
    m["To"] = "margaret@example.org"
    m["Subject"] = "Your Medicare Summary Notice"
    m["DKIM-Signature"] = "v=1; a=rsa-sha256; d=medicare.gov; s=s1; b=abc"
    m["Authentication-Results"] = "mx.example.org; spf=pass; dkim=pass; dmarc=pass"
    m.set_content(f"Your notice for October is ready. {SENTINEL}")
    m.add_alternative(
        f"<p>Your notice for October is ready. {SENTINEL}</p>"
        '<p><a href="https://www.medicare.gov/account">www.medicare.gov</a></p>',
        subtype="html")
    return bytes(m)


# --- 1. The tricks a raw-text scan could not see -------------------------------

def test_a_real_phishing_message_is_dangerous_and_says_why():
    from cura.privacy.email_intake import scan_raw_email
    v = scan_raw_email(_phish())
    joined = " | ".join(v.indicators)
    assert v.risk_level == "dangerous", joined
    assert "A link shows medicare.gov but goes to 203.0.113.9" in v.indicators, joined
    assert "Name says medicare but the address is medicare-help.xyz" in v.indicators, joined
    assert any(i.startswith("SPF check FAILED at her mail server") for i in v.indicators), joined
    assert any(i.startswith("DMARC check FAILED at her mail server") for i in v.indicators), joined
    assert "Replies go to example.net, not medicare-help.xyz" in v.indicators, joined


@pytest.mark.parametrize("trick", ["link", "name", "auth"])
def test_each_trick_alone_is_seen(trick):
    """One at a time, so a scanner that only catches the obvious pile-up fails."""
    from cura.privacy.email_intake import scan_raw_email
    m = EmailMessage()
    m["From"] = ('"Medicare" <help@benefits-desk.example.com>' if trick == "name"
                 else '"A friend" <pat@example.com>')
    m["Subject"] = "hello"
    m["DKIM-Signature"] = "v=1; d=example.com"
    m["Authentication-Results"] = ("mx; spf=pass; dkim=fail; dmarc=pass" if trick == "auth"
                                   else "mx; spf=pass; dkim=pass; dmarc=pass")
    m.set_content("see below")
    if trick == "link":
        m.add_alternative('<a href="https://login.evil.example/x">www.chase.com</a>',
                          subtype="html")
    v = scan_raw_email(bytes(m))
    want = {"link": "A link shows chase.com but goes to login.evil.example",
            "name": "Name says medicare but the address is benefits-desk.example.com",
            "auth": "DKIM check FAILED at her mail server — sender may be spoofed"}[trick]
    assert want in v.indicators, v.indicators


def test_a_real_medicare_notice_is_safe():
    from cura.privacy.email_intake import scan_raw_email
    v = scan_raw_email(_legit())
    assert v.risk_level == "safe", v.indicators
    assert v.indicators == [], v.indicators


def test_something_that_is_not_an_email_is_refused_not_called_safe():
    from cura.privacy.email_intake import scan_raw_email
    try:
        v = scan_raw_email(b"just some words, no headers at all")
    except ValueError:
        return
    assert False, f"a non-email was scanned and called {v.risk_level!r}"


# --- 2 and 3. Through the real entry points ------------------------------------

def _cli(monkeypatch, capsys, path) -> tuple[int, str]:
    monkeypatch.setattr(sys, "argv", ["cura", "scan-email", str(path)])
    from cura.__main__ import main
    with pytest.raises(SystemExit) as e:
        main()
    return e.value.code, capsys.readouterr().out


def _home_files(home):
    return sorted(str(p.relative_to(home)) for p in home.rglob("*"))


@pytest.mark.parametrize("which", ["phish", "legit"])
def test_cura_scan_email_says_what_it_found_keeps_nothing_tells_nobody(
        which, tmp_path, monkeypatch, capsys, sent):
    from pathlib import Path
    home = Path.home()
    eml = tmp_path / "message.eml"
    eml.write_bytes(_phish() if which == "phish" else _legit())
    before = _home_files(home)
    code, out = _cli(monkeypatch, capsys, eml)
    assert code == 0, out
    assert SENTINEL not in out, "the body came back out"
    assert _text_claims_alert(out) == [], out
    assert not sent, f"scanning one email sent something: {sent}"
    assert "didn't tell anyone" in out, out
    assert _home_files(home) == before, "scanning wrote to her Cura folder"
    if which == "phish":
        assert "looks like a scam" in out and "medicare.gov" in out, out
    else:
        assert "didn't find anything wrong" in out, out


def test_cura_scan_email_on_a_file_that_is_not_an_email(tmp_path, monkeypatch, capsys):
    f = tmp_path / "notes.txt"
    f.write_text("shopping list: milk, eggs")
    code, out = _cli(monkeypatch, capsys, f)
    assert code == 1 and "doesn't look like an email" in out, out


@pytest.mark.parametrize("which", ["phish", "legit"])
def test_the_mcp_scam_check_reads_a_whole_email(which, sent, mcp_call):
    raw = (_phish() if which == "phish" else _legit()).decode()
    payload = mcp_call("cura_scam_check", {"email": raw})
    text = json.dumps(payload)
    assert SENTINEL not in text, "the body came back out"
    assert payload["caregiver_alerted"] is False, payload
    claims = _payload_claims_alert(payload)
    assert not claims or sent, f"claimed {claims} with nothing sent: {payload}"
    if which == "phish":
        assert payload["risk_level"] == "dangerous", payload
        assert payload["scam_detected"] is True, payload
    else:
        assert payload["risk_level"] == "safe" and payload["status"] == "clean", payload


def test_the_mcp_scam_check_still_reads_a_message(sent, mcp_call):
    """The old argument keeps working."""
    payload = mcp_call("cura_scam_check", {"message": "They want me to wire money today"})
    assert payload["status"] == "alert", payload


# --- The scanner's own words ---------------------------------------------------

def test_the_scanner_promises_no_alert_and_no_block():
    """Its dangerous verdict said "Cura will alert your caregiver", and its daily
    summary said messages were "blocked" with "Details in the caregiver
    dashboard". Nothing alerts anyone, nothing blocks mail, and cura/dashboard/
    is empty."""
    from cura.privacy.email_intake import scan_raw_email
    from cura.privacy.message_scanner import MessageScanner
    scanner = MessageScanner()
    v = scan_raw_email(_phish(), scanner=scanner)
    assert v.risk_level == "dangerous"
    assert _text_claims_alert(v.recommended_action) == [], v.recommended_action
    assert "caregiver" not in v.recommended_action.lower(), v.recommended_action
    summary = scanner.daily_summary()
    assert "blocked" not in summary.lower() and "dashboard" not in summary.lower(), summary
