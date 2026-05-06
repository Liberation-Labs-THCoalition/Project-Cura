"""Tests for scam shield — proactive fraud defense."""
from __future__ import annotations

from cura.privacy.scam_shield import ScamShield, ScamAlert


class TestScamShield:
    def test_education_tip_rotation(self):
        shield = ScamShield(education_frequency=2, screening_frequency=100)
        shield._checkin_count = 1
        tip = shield.get_checkin_addition()
        assert tip is not None
        assert "Quick safety reminder" in tip

    def test_screening_question(self):
        shield = ScamShield(education_frequency=100, screening_frequency=3)
        shield._checkin_count = 2
        question = shield.get_checkin_addition()
        assert question is not None
        assert "?" in question

    def test_no_addition_on_off_cycle(self):
        shield = ScamShield(education_frequency=5, screening_frequency=7)
        result = shield.get_checkin_addition()
        assert result is None

    def test_detect_wire_request(self):
        shield = ScamShield()
        alert = shield.analyze_response("Someone asked me to wire money to them")
        assert alert is not None
        assert alert.severity >= 0.8
        assert "URGENT" in alert.recommended_action

    def test_detect_gift_card_scam(self):
        shield = ScamShield()
        alert = shield.analyze_response("They said to pay with gift cards from Walmart")
        assert alert is not None
        assert alert.severity >= 0.8

    def test_detect_secrecy_request(self):
        shield = ScamShield()
        alert = shield.analyze_response("He told me not to tell anyone about the payment")
        assert alert is not None
        assert alert.severity >= 0.8
        assert "HIGH" in alert.recommended_action

    def test_detect_dont_tell_family(self):
        shield = ScamShield()
        alert = shield.analyze_response("She said not to tell your family about this")
        assert alert is not None
        assert alert.severity >= 0.8

    def test_detect_irs_scam(self):
        shield = ScamShield()
        alert = shield.analyze_response("The IRS called and said I'd be arrested")
        assert alert is not None
        assert "Government impostor" in alert.recommended_action

    def test_detect_grandchild_scam(self):
        shield = ScamShield()
        alert = shield.analyze_response("My grandson called and said he's in jail")
        assert alert is not None
        assert "grandchild" in alert.recommended_action.lower()

    def test_clean_response_no_alert(self):
        shield = ScamShield()
        alert = shield.analyze_response("I had a lovely day in the garden")
        assert alert is None

    def test_reassurance_message(self):
        shield = ScamShield()
        msg = shield.get_reassurance()
        assert "right thing" in msg
        assert "trust" in msg.lower()

    def test_unnotified_alerts(self):
        shield = ScamShield()
        shield.analyze_response("Someone asked me to wire money")
        assert len(shield.unnotified_alerts) == 1
        shield.alerts[0].caregiver_notified = True
        assert len(shield.unnotified_alerts) == 0


class TestMessageScannerIntegration:
    def test_medicare_phishing(self):
        from cura.privacy.message_scanner import MessageScanner
        scanner = MessageScanner()
        verdict = scanner.scan_email(
            sender="claims@medicare-update.xyz",
            subject="URGENT: Your Medicare Card Is Suspended",
            body="Your Medicare account has been compromised. Click here now to verify: http://medicare-update.xyz/verify",
            headers={"Received-SPF": "fail"},
        )
        assert verdict.risk_level == "dangerous"
        assert verdict.risk_score >= 0.6

    def test_legitimate_medicare(self):
        from cura.privacy.message_scanner import MessageScanner
        scanner = MessageScanner()
        verdict = scanner.scan_email(
            sender="noreply@medicare.gov",
            subject="Your Medicare Summary Notice",
            body="Your Medicare Summary Notice for January 2026 is available. Visit medicare.gov to view it.",
            headers={"DKIM-Signature": "v=1; d=medicare.gov", "Received-SPF": "pass"},
        )
        assert verdict.risk_level == "safe"

    def test_suspicious_sms(self):
        from cura.privacy.message_scanner import MessageScanner
        scanner = MessageScanner()
        verdict = scanner.scan_sms(
            sender="+442012345678",
            body="Your account has been compromised! Act now: http://bit.ly/fix-account",
        )
        assert verdict.risk_level != "safe"

    def test_clean_sms(self):
        from cura.privacy.message_scanner import MessageScanner
        scanner = MessageScanner()
        verdict = scanner.scan_sms(
            sender="+15551234567",
            body="Hi grandma, see you for dinner Sunday! Love you.",
        )
        assert verdict.risk_level == "safe"

    def test_daily_summary_no_threats(self):
        from cura.privacy.message_scanner import MessageScanner
        scanner = MessageScanner()
        summary = scanner.daily_summary()
        assert "No suspicious" in summary
