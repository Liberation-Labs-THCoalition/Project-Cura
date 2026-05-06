"""Scam Shield — protecting elders from fraud and exploitation.

Cura talks to Margaret every day. That daily relationship is the
most powerful scam defense possible: a trusted presence who asks
the right questions before the money leaves the account.

Three layers:
  1. Proactive education — gentle reminders woven into check-ins
  2. Daily screening — "has anyone asked you for money today?"
  3. Pattern alerts — flag behavioral changes to caregivers

Common scams targeting elders:
  - IRS/SSA impostor calls ("you owe taxes, pay now or be arrested")
  - Medicare fraud ("we need your Medicare number to send your new card")
  - Grandchild emergency ("grandma, I'm in jail, wire money")
  - Tech support ("your computer has a virus, give us remote access")
  - Romance scams (online relationship → financial exploitation)
  - Sweepstakes ("you've won! Pay the processing fee")
  - Home repair ("your roof needs fixing, pay upfront")
  - Charity fraud (fake charities after disasters)

The shield doesn't monitor calls or read email — that's surveillance.
It ASKS and EDUCATES during the conversations Cura already has.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ScamAlert:
    """A potential scam indicator detected during conversation."""
    timestamp: datetime
    alert_type: str
    description: str
    severity: float  # 0-1
    elder_statement: str = ""
    recommended_action: str = ""
    caregiver_notified: bool = False


# Scam education tips — one per check-in, rotated
EDUCATION_TIPS = [
    "Remember, the IRS will never call and demand immediate payment. If someone says they're from the IRS, hang up and call me.",
    "Medicare will never call you asking for your Medicare number. You already have your card — nobody needs to send a new one.",
    "If someone calls saying a grandchild is in trouble and needs money, hang up and call your grandchild directly to check.",
    "No real prize or lottery requires you to pay a fee to collect your winnings. If they ask for money, it's a scam.",
    "Never give remote access to your computer to someone who calls you. Real tech companies don't call about viruses.",
    "If a repair person shows up and demands payment upfront before doing any work, that's a warning sign.",
    "Be cautious of new online friendships that quickly turn to requests for money. Real friends don't ask for wire transfers.",
    "Your bank will never call and ask for your full account number or PIN. If they do, hang up and call the number on your card.",
    "If someone pressures you to decide RIGHT NOW, that's a red flag. Real opportunities give you time to think.",
    "It's always okay to say 'let me check with my family first.' Anyone who objects to that is not looking out for you.",
    "Free trials that ask for your credit card number often turn into charges. Read the fine print or ask someone you trust.",
    "If a charity calls asking for donations right after a disaster, look them up on charitynavigator.org before giving.",
]

# Keywords that suggest an elder may have been targeted
CONCERN_KEYWORDS = [
    "wire", "gift card", "money gram", "western union",
    "won a prize", "lottery", "sweepstakes",
    "irs", "social security", "medicare card",
    "grandson", "granddaughter", "in jail", "in trouble",
    "computer virus", "remote access", "tech support",
    "processing fee", "pay immediately", "arrest",
    "keep this secret", "don't tell anyone", "not to tell anyone",
    "keep it between us", "our little secret", "don't tell your family",
    "not to tell your family", "just between us",
    "new friend online", "met someone",
    "pay upfront", "cash only",
    "your account has been compromised",
]


class ScamShield:
    """Proactive scam defense woven into daily conversations.

    Not surveillance — education and gentle screening.

    Args:
        education_frequency: How often to include a tip (1 = every check-in)
        screening_frequency: How often to ask about suspicious contacts
    """

    def __init__(
        self,
        education_frequency: int = 2,  # every 2nd check-in
        screening_frequency: int = 3,  # every 3rd check-in
    ) -> None:
        self._edu_freq = education_frequency
        self._screen_freq = screening_frequency
        self._checkin_count = 0
        self._tip_index = 0
        self._alerts: list[ScamAlert] = []
        self._rng = random.Random(42)

    def get_checkin_addition(self) -> str | None:
        """Get an optional scam-awareness addition for the current check-in.

        Returns a tip or screening question, or None if this check-in
        doesn't include one. Alternates between education and screening.
        """
        self._checkin_count += 1

        if self._checkin_count % self._screen_freq == 0:
            return self._get_screening_question()
        elif self._checkin_count % self._edu_freq == 0:
            return self._get_education_tip()
        return None

    def _get_education_tip(self) -> str:
        """Get the next education tip in rotation."""
        tip = EDUCATION_TIPS[self._tip_index % len(EDUCATION_TIPS)]
        self._tip_index += 1
        return f"Quick safety reminder: {tip}"

    def _get_screening_question(self) -> str:
        """Get a gentle screening question."""
        questions = [
            "By the way, has anyone called you recently asking for money or personal information?",
            "Has anyone asked you to buy gift cards or wire money for any reason?",
            "Have you gotten any calls about your Medicare card or Social Security number?",
            "Has anyone new been asking you for help with money recently?",
            "Has anyone told you to keep a phone call or payment secret from your family?",
        ]
        return self._rng.choice(questions)

    def analyze_response(self, elder_statement: str) -> ScamAlert | None:
        """Analyze an elder's response for scam indicators.

        This runs on the elder's verbal response during check-ins.
        Flags concerning keywords for caregiver review.
        """
        statement_lower = elder_statement.lower()

        triggered_keywords = [
            kw for kw in CONCERN_KEYWORDS
            if kw in statement_lower
        ]

        if not triggered_keywords:
            return None

        severity = min(1.0, len(triggered_keywords) * 0.3)

        # High severity indicators
        if any(kw in statement_lower for kw in [
            "keep this secret", "don't tell anyone", "not to tell anyone",
            "keep it between us", "our little secret", "just between us",
            "don't tell your family", "not to tell your family",
            "wire", "gift card", "pay immediately",
        ]):
            severity = max(severity, 0.8)

        alert = ScamAlert(
            timestamp=datetime.now(timezone.utc),
            alert_type="potential_scam_indicators",
            description=f"Keywords detected: {', '.join(triggered_keywords)}",
            severity=severity,
            elder_statement=elder_statement[:200],
            recommended_action=self._recommend_action(triggered_keywords),
        )
        self._alerts.append(alert)
        return alert

    def _recommend_action(self, keywords: list[str]) -> str:
        """Recommend action based on detected keywords."""
        if any(kw in keywords for kw in ["wire", "gift card", "money gram", "western union"]):
            return "URGENT: Ask caregiver to verify. Elder may have been asked to send money."
        if any(kw in keywords for kw in [
            "keep this secret", "don't tell anyone", "not to tell anyone",
            "keep it between us", "our little secret", "just between us",
            "don't tell your family", "not to tell your family",
        ]):
            return "HIGH: Secrecy request is a major red flag. Alert caregiver immediately."
        if any(kw in keywords for kw in ["irs", "social security", "arrest"]):
            return "Government impostor scam likely. Reassure elder that real agencies don't threaten arrest."
        if any(kw in keywords for kw in ["grandson", "granddaughter", "in jail", "in trouble"]):
            return "Possible grandchild emergency scam. Ask elder to call the grandchild directly."
        if any(kw in keywords for kw in ["computer virus", "remote access", "tech support"]):
            return "Tech support scam likely. Advise elder to hang up and not give remote access."
        return "Monitor situation. Discuss with caregiver at next check-in."

    def get_reassurance(self) -> str:
        """A reassuring message when an elder reports a suspicious contact."""
        return (
            "Thank you for telling me about that. You did the right thing. "
            "I'm going to let your family know so they can help look into it. "
            "Remember, it's never wrong to check with someone you trust before "
            "giving out information or sending money."
        )

    @property
    def alerts(self) -> list[ScamAlert]:
        return list(self._alerts)

    @property
    def unnotified_alerts(self) -> list[ScamAlert]:
        return [a for a in self._alerts if not a.caregiver_notified]
