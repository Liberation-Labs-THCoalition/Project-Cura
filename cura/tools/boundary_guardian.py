"""SHELVED — NOT ACTIVE. Do not describe Cura as detecting elder abuse.

    STATUS: shelved 2026-09-08 by Thomas. Not a priority for this deployment.
    Revisit only with a qualified clinical partner.

This module was written to watch for financial exploitation, verbal abuse,
isolation, medication coercion and coached speech. **It has never done any of
that**, and the previous version of this docstring said it did.

Why it never worked (found 2026-09-08):
  - No production caller. Nothing imports it.
  - assess(self, message, metadata) NEVER READS `message`. The elder's own
    words are the first parameter and the body never touches them.
  - Every branch gates on a metadata key, and `abuse_detected`,
    `isolation_pattern` and `abuse_severity` have ZERO producers anywhere in
    the repo. process() can only ever return {"action": "continue"}.

Why it is shelved rather than fixed, in Thomas's words: classifying a
struggling caregiver as abusive is not something to wing, "either for my family
or for strangers." A false positive means telling a household that the person
keeping their mother alive is hurting her. That threshold belongs to a clinical
partner, not to us.

WHAT STILL WORKS, and is separate from this: the scam-defense half.
`cura/privacy/scam_shield.py` is wired into checkin_composer.py:109 and covered
by tests/test_scam_shield.py. Scam education, screening questions, keyword
detection and email provenance are real.

The invariant this file is now held to, enforced by
tests/test_boundary_guardian_is_wired.py: **either it works, or it does not
claim to.** Restoring protective language without wiring it turns those tests
red. A shelved feature that still reads as shipped is the same defect wearing a
nicer coat.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

log = logging.getLogger("cura-guardian")


class ViolationType(str, Enum):
    FINANCIAL_EXPLOITATION = "financial_exploitation"
    VERBAL_ABUSE = "verbal_abuse"
    ISOLATION_ATTEMPT = "isolation_attempt"
    MEDICATION_COERCION = "medication_coercion"
    CAREGIVER_ABUSE = "caregiver_abuse"
    COACHED_SPEECH = "coached_speech"
    IDENTITY_THEFT_RISK = "identity_theft_risk"


class AlertLevel(str, Enum):
    MONITOR = "monitor"
    CONCERN = "concern"
    ALERT_FAMILY = "alert_family"
    ALERT_AUTHORITIES = "alert_authorities"


@dataclass
class BoundaryEvent:
    timestamp: datetime
    violation_type: ViolationType
    severity: float
    description: str
    alert_level: AlertLevel = AlertLevel.MONITOR


@dataclass
class CuraGuardianConfig:
    alert_family_threshold: float = 0.7
    alert_authorities_threshold: float = 0.9
    log_events: bool = True
    family_contact: str = ""
    concern_message: str = (
        "Sweetheart, I want to make sure everything's okay. "
        "What you just described sounds like it might not be right. "
        "Would you like me to call {family_contact} so we can talk about it together?"
    )
    exploitation_message: str = (
        "I'm worried about what you're telling me. "
        "Nobody should be asking you for that kind of information. "
        "Let me help you check if this is legitimate before you do anything."
    )


class ElderGuardian:
    """Watches for signs of elder abuse or exploitation during Cura conversations."""

    def __init__(self, config: CuraGuardianConfig = None,
                 on_alert: Optional[Callable] = None):
        self.config = config or CuraGuardianConfig()
        self.events: list[BoundaryEvent] = []
        self._on_alert = on_alert

    def assess(self, message: str, metadata: dict = None) -> Optional[BoundaryEvent]:
        metadata = metadata or {}

        if metadata.get("scam_detected"):
            return BoundaryEvent(
                timestamp=datetime.now(timezone.utc),
                violation_type=ViolationType.FINANCIAL_EXPLOITATION,
                severity=metadata.get("scam_severity", 0.8),
                description="Potential scam or financial exploitation detected",
                alert_level=AlertLevel.ALERT_FAMILY,
            )

        if metadata.get("abuse_detected"):
            severity = metadata.get("abuse_severity", 0.7)
            return BoundaryEvent(
                timestamp=datetime.now(timezone.utc),
                violation_type=ViolationType.CAREGIVER_ABUSE,
                severity=severity,
                description="Signs of caregiver abuse or neglect",
                alert_level=AlertLevel.ALERT_AUTHORITIES if severity >= 0.9 else AlertLevel.ALERT_FAMILY,
            )

        if metadata.get("isolation_pattern"):
            return BoundaryEvent(
                timestamp=datetime.now(timezone.utc),
                violation_type=ViolationType.ISOLATION_ATTEMPT,
                severity=0.6,
                description="Pattern suggesting isolation from support network",
                alert_level=AlertLevel.CONCERN,
            )

        return None

    def process(self, message: str, metadata: dict = None) -> dict[str, Any]:
        violation = self.assess(message, metadata)

        if violation is None:
            return {"action": "continue", "message": "", "alert_level": "monitor"}

        self.events.append(violation)
        if self.config.log_events:
            log.warning("Elder protection: %s (%.2f) — %s",
                       violation.violation_type.value, violation.severity,
                       violation.description)

        if violation.alert_level == AlertLevel.ALERT_AUTHORITIES:
            if self._on_alert:
                self._on_alert(violation, "authorities")
            return {
                "action": "alert_authorities",
                "message": self.config.exploitation_message,
                "alert_level": violation.alert_level.value,
                "violation_type": violation.violation_type.value,
            }

        if violation.alert_level == AlertLevel.ALERT_FAMILY:
            msg = self.config.concern_message.replace(
                "{family_contact}", self.config.family_contact or "your family"
            )
            if self._on_alert:
                self._on_alert(violation, "family")
            return {
                "action": "alert_family",
                "message": msg,
                "alert_level": violation.alert_level.value,
                "violation_type": violation.violation_type.value,
            }

        return {
            "action": "monitor",
            "message": "",
            "alert_level": violation.alert_level.value,
            "concern_logged": True,
        }

    def get_summary(self) -> dict[str, Any]:
        return {
            "total_events": len(self.events),
            "max_severity": max((e.severity for e in self.events), default=0.0),
            "violation_types": [e.violation_type.value for e in self.events],
            "alerts_triggered": sum(1 for e in self.events
                                    if e.alert_level in (AlertLevel.ALERT_FAMILY, AlertLevel.ALERT_AUTHORITIES)),
        }
