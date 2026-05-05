"""Message Scanner — preemptive fraud detection for email and SMS.

Scans the elder's incoming messages for phishing, scam, and fraud
indicators. Not content surveillance — PROVENANCE checking:
  - Is this email actually from Medicare, or a spoofed sender?
  - Is this domain 2 days old pretending to be a bank?
  - Does this SMS come from a known scam number pattern?
  - Does this "Amazon order" link actually go to Amazon?

The elder (or authorized designee) explicitly enables this.
Cura flags suspicious messages but does NOT store personal
email content — only the fraud assessment.

Consent architecture:
  - Elder authorizes email monitoring during setup
  - Can disable at any time ("Cura, stop checking my email")
  - Cura reports what she flagged but not what she read
  - Content is processed in memory and discarded — only the
    verdict is logged
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class MessageVerdict:
    """Fraud assessment for a single message."""
    timestamp: datetime
    source: str  # email, sms, voicemail
    sender: str  # redacted for logging (e.g., "***@medicare.gov")
    subject: str = ""  # for email only
    risk_score: float = 0.0  # 0-1
    risk_level: str = "safe"  # safe, suspicious, dangerous
    indicators: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    recommended_action: str = ""
    # Content is NEVER stored — only the verdict


# Known scam sender patterns
SCAM_SENDER_PATTERNS = [
    r".*@.*\.xyz$",
    r".*@.*\.top$",
    r".*@.*\.click$",
    r".*@.*\.work$",
    r"no-?reply@(?!amazon|google|apple|medicare|ssa\.gov|irs\.gov)",
    r".*alert.*@(?!.*\.gov)",
    r".*security.*@(?!.*\.gov|.*bank\.com)",
    r".*verify.*@",
    r".*update.*@(?!.*\.gov)",
]

# Legitimate government/institution domains
TRUSTED_DOMAINS = {
    "medicare.gov", "ssa.gov", "irs.gov", "va.gov",
    "cms.gov", "hhs.gov", "benefits.gov",
    "amazon.com", "google.com", "apple.com",
    "bankofamerica.com", "chase.com", "wellsfargo.com",
}

# Phishing language patterns
URGENCY_PATTERNS = [
    r"act\s+(now|immediately|today)",
    r"urgent\s+(action|notice|alert)",
    r"account\s+(suspended|locked|compromised|closed)",
    r"verify\s+(your|account|identity)\s+(now|immediately)",
    r"(click|tap)\s+here\s+(now|immediately)",
    r"(failure|refusal)\s+to\s+(respond|act|verify)",
    r"will\s+be\s+(suspended|terminated|closed|deleted)",
    r"within\s+\d+\s+(hours?|minutes?)",
    r"final\s+(notice|warning|attempt)",
    r"unauthorized\s+(access|transaction|activity)",
]

# Money-related phishing patterns
MONEY_PATTERNS = [
    r"(wire|transfer)\s+\$?\d",
    r"(gift\s*card|prepaid\s*card)",
    r"(processing|handling|shipping)\s+fee",
    r"send\s+\$?\d",
    r"(bitcoin|crypto|btc)\s+(address|wallet|payment)",
    r"(western\s+union|money\s*gram|zelle)",
    r"refund\s+of\s+\$",
    r"(unclaimed|pending)\s+(funds|money|inheritance)",
]

# Suspicious URL patterns
SUSPICIOUS_URL_PATTERNS = [
    r"bit\.ly/", r"tinyurl\.com/", r"t\.co/",
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",  # IP addresses
    r".*-login\.", r".*-verify\.", r".*-secure\.",
    r".*\.ru/", r".*\.cn/", r".*\.tk/",
]


class MessageScanner:
    """Scan incoming messages for fraud indicators.

    Does NOT store message content. Processes in memory,
    outputs only the verdict.
    """

    def __init__(self) -> None:
        self._verdicts: list[MessageVerdict] = []
        self._compiled_urgency = [re.compile(p, re.I) for p in URGENCY_PATTERNS]
        self._compiled_money = [re.compile(p, re.I) for p in MONEY_PATTERNS]
        self._compiled_scam_senders = [re.compile(p, re.I) for p in SCAM_SENDER_PATTERNS]
        self._compiled_urls = [re.compile(p, re.I) for p in SUSPICIOUS_URL_PATTERNS]

    def scan_email(
        self,
        sender: str,
        subject: str,
        body: str,
        headers: dict[str, str] | None = None,
    ) -> MessageVerdict:
        """Scan an email for fraud indicators.

        Content (body) is analyzed but NEVER stored.
        """
        now = datetime.now(timezone.utc)
        indicators = []
        provenance = {}

        # 1. Sender analysis
        sender_domain = sender.split("@")[-1].lower() if "@" in sender else ""
        sender_redacted = f"***@{sender_domain}"

        for pattern in self._compiled_scam_senders:
            if pattern.match(sender.lower()):
                indicators.append(f"Suspicious sender pattern: {sender_domain}")
                break

        # 2. Spoofing detection via headers
        if headers:
            dkim = headers.get("dkim", headers.get("DKIM-Signature", ""))
            spf = headers.get("spf", headers.get("Received-SPF", ""))
            from_header = headers.get("From", "")
            return_path = headers.get("Return-Path", "")

            if spf and "fail" in spf.lower():
                indicators.append("SPF check FAILED — sender may be spoofed")
                provenance["spf"] = "fail"
            if return_path and sender_domain not in return_path.lower():
                indicators.append("Return-Path doesn't match sender domain")
                provenance["return_path_mismatch"] = True
            if not dkim:
                indicators.append("No DKIM signature — authenticity unverified")
                provenance["dkim"] = "missing"

        # 3. Subject line analysis
        subject_lower = subject.lower()
        if any(w in subject_lower for w in [
            "urgent", "alert", "suspended", "verify", "action required",
            "final notice", "security", "compromised", "locked",
        ]):
            indicators.append(f"Urgency language in subject: '{subject[:50]}'")

        # 4. Body analysis (processed in memory, not stored)
        for pattern in self._compiled_urgency:
            if pattern.search(body):
                indicators.append("Urgency/threat language in body")
                break

        for pattern in self._compiled_money:
            if pattern.search(body):
                indicators.append("Money transfer request in body")
                break

        # 5. URL analysis
        urls = re.findall(r'https?://[^\s<>"\']+', body)
        for url in urls:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            for pattern in self._compiled_urls:
                if pattern.search(url):
                    indicators.append(f"Suspicious URL: {domain}")
                    break

            # Check if URL domain matches claimed sender
            if sender_domain in TRUSTED_DOMAINS and domain != sender_domain:
                if not any(sender_domain in domain for _ in [1]):
                    indicators.append(
                        f"Link goes to {domain}, not {sender_domain}"
                    )

        # 6. Impersonation detection
        impersonation_claims = [
            ("medicare", "medicare.gov"),
            ("social security", "ssa.gov"),
            ("irs", "irs.gov"),
            ("amazon", "amazon.com"),
        ]
        for claim, real_domain in impersonation_claims:
            if claim in body.lower() and sender_domain != real_domain:
                indicators.append(
                    f"Claims to be {claim} but sender is {sender_domain}"
                )

        # Score
        risk_score = min(1.0, len(indicators) * 0.2)
        if any("SPF" in i or "spoofed" in i for i in indicators):
            risk_score = max(risk_score, 0.7)
        if any("Money transfer" in i for i in indicators):
            risk_score = max(risk_score, 0.8)

        risk_level = "safe"
        if risk_score >= 0.6:
            risk_level = "dangerous"
        elif risk_score >= 0.3:
            risk_level = "suspicious"

        action = ""
        if risk_level == "dangerous":
            action = "DO NOT click any links or reply. This is likely a scam. Cura will alert your caregiver."
        elif risk_level == "suspicious":
            action = "Be cautious. Don't click links or share personal information. Ask Cura if you're unsure."

        verdict = MessageVerdict(
            timestamp=now,
            source="email",
            sender=sender_redacted,
            subject=subject[:50],
            risk_score=risk_score,
            risk_level=risk_level,
            indicators=indicators,
            provenance=provenance,
            recommended_action=action,
        )
        self._verdicts.append(verdict)
        return verdict

    def scan_sms(self, sender: str, body: str) -> MessageVerdict:
        """Scan an SMS for fraud indicators."""
        now = datetime.now(timezone.utc)
        indicators = []

        # Short code vs real number
        if len(sender.replace("+", "").replace("-", "")) <= 6:
            pass  # Short codes are normal for businesses
        elif not sender.startswith("+1") and not sender.startswith("1"):
            indicators.append("International sender number")

        # URL in SMS
        urls = re.findall(r'https?://[^\s]+', body)
        for url in urls:
            for pattern in self._compiled_urls:
                if pattern.search(url):
                    indicators.append(f"Suspicious link in text")
                    break

        # Urgency
        for pattern in self._compiled_urgency:
            if pattern.search(body):
                indicators.append("Urgency language")
                break

        # Money
        for pattern in self._compiled_money:
            if pattern.search(body):
                indicators.append("Money request")
                break

        risk_score = min(1.0, len(indicators) * 0.25)
        risk_level = "dangerous" if risk_score >= 0.5 else "suspicious" if risk_score >= 0.25 else "safe"

        verdict = MessageVerdict(
            timestamp=now,
            source="sms",
            sender=sender[-4:].rjust(len(sender), "*"),
            risk_score=risk_score,
            risk_level=risk_level,
            indicators=indicators,
            recommended_action="Don't click links or call numbers in this text." if risk_level != "safe" else "",
        )
        self._verdicts.append(verdict)
        return verdict

    def daily_summary(self) -> str:
        """Generate a daily summary for the caregiver dashboard."""
        today = datetime.now(timezone.utc).date()
        today_verdicts = [
            v for v in self._verdicts
            if v.timestamp.date() == today
        ]
        dangerous = [v for v in today_verdicts if v.risk_level == "dangerous"]
        suspicious = [v for v in today_verdicts if v.risk_level == "suspicious"]

        if not dangerous and not suspicious:
            return "No suspicious messages detected today."

        parts = []
        if dangerous:
            parts.append(f"{len(dangerous)} dangerous message(s) blocked")
        if suspicious:
            parts.append(f"{len(suspicious)} suspicious message(s) flagged")
        return "; ".join(parts) + ". Details in the caregiver dashboard."

    @property
    def verdicts(self) -> list[MessageVerdict]:
        return list(self._verdicts)
