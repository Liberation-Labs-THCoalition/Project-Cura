"""Voice interface — Cura's ability to call and speak.

Uses Twilio for outbound calls and SMS. The voice is warm,
patient, and never rushed. Cura speaks like a neighbor checking
in, not a system running a script.

Phase 1: Twilio Voice (outbound calls) + SMS
Phase 2: Inbound call handling (elder calls Cura)
Phase 3: Voice analysis (detect confusion, distress)

Usage:
    voice = CuraVoice(twilio_sid, twilio_token, from_number)
    await voice.morning_checkin(elder_profile)
    await voice.medication_reminder(elder_profile, medications)
    await voice.send_sms(to_number, "Your refill is ready for pickup.")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class CallResult:
    """Result of a voice call attempt."""
    timestamp: datetime
    to_number: str
    answered: bool
    duration_seconds: int = 0
    call_sid: str = ""
    transcript: str = ""
    elder_response: str = ""
    error: str = ""


@dataclass
class SMSResult:
    """Result of an SMS send."""
    timestamp: datetime
    to_number: str
    delivered: bool
    message_sid: str = ""
    error: str = ""


class CuraVoice:
    """Cura's voice — warm, patient outbound calls and texts.

    Args:
        account_sid: Twilio account SID
        auth_token: Twilio auth token
        from_number: Twilio phone number (E.164 format)
        tts_voice: Twilio TTS voice name (default: warm female)
        speech_rate: Speaking speed (slow for elderly listeners)
    """

    def __init__(
        self,
        account_sid: str = "",
        auth_token: str = "",
        from_number: str = "",
        tts_voice: str = "Polly.Joanna",
        speech_rate: str = "slow",
        dry_run: bool = False,
    ) -> None:
        self._sid = account_sid
        self._token = auth_token
        self._from = from_number
        self._voice = tts_voice
        self._rate = speech_rate
        self._dry_run = dry_run
        self._call_log: list[CallResult] = []
        self._sms_log: list[SMSResult] = []
        self._client = None

    def _get_client(self):
        """Lazy-initialize Twilio client."""
        if self._client is None and not self._dry_run:
            try:
                from twilio.rest import Client
                self._client = Client(self._sid, self._token)
            except ImportError:
                logger.warning("twilio package not installed — running in dry-run mode")
                self._dry_run = True
        return self._client

    def _build_twiml(self, messages: list[str], gather: bool = False) -> str:
        """Build TwiML for a voice call.

        Args:
            messages: List of sentences to speak
            gather: If True, wait for keypad input after speaking
        """
        parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<Response>']

        if gather:
            parts.append(f'  <Gather input="dtmf speech" timeout="10" numDigits="1">')

        for msg in messages:
            parts.append(
                f'  <Say voice="{self._voice}" rate="{self._rate}">'
                f'{msg}</Say>'
            )
            parts.append('  <Pause length="1"/>')

        if gather:
            parts.append('  </Gather>')
            parts.append(f'  <Say voice="{self._voice}" rate="{self._rate}">'
                         f'I didn\'t hear a response. I\'ll check back later. '
                         f'Take care.</Say>')

        parts.append('</Response>')
        return '\n'.join(parts)

    async def call(
        self,
        to_number: str,
        messages: list[str],
        gather_response: bool = False,
        status_callback: str = "",
    ) -> CallResult:
        """Place an outbound voice call.

        Args:
            to_number: Phone number to call (E.164)
            messages: Sentences to speak
            gather_response: Wait for keypad/voice response
            status_callback: URL for call status webhooks
        """
        now = datetime.now(timezone.utc)
        twiml = self._build_twiml(messages, gather=gather_response)

        if self._dry_run:
            logger.info("[DRY RUN] Call to %s: %s", to_number, " | ".join(messages))
            result = CallResult(
                timestamp=now,
                to_number=to_number,
                answered=True,
                duration_seconds=len(messages) * 5,
                call_sid="dry_run",
                transcript=" ".join(messages),
            )
            self._call_log.append(result)
            return result

        client = self._get_client()
        if not client:
            return CallResult(
                timestamp=now, to_number=to_number, answered=False,
                error="No Twilio client available",
            )

        try:
            call = client.calls.create(
                twiml=twiml,
                to=to_number,
                from_=self._from,
                status_callback=status_callback or None,
            )
            result = CallResult(
                timestamp=now,
                to_number=to_number,
                answered=True,
                call_sid=call.sid,
                transcript=" ".join(messages),
            )
        except Exception as e:
            result = CallResult(
                timestamp=now, to_number=to_number, answered=False,
                error=str(e),
            )

        self._call_log.append(result)
        return result

    async def send_sms(self, to_number: str, message: str) -> SMSResult:
        """Send an SMS message."""
        now = datetime.now(timezone.utc)

        if self._dry_run:
            logger.info("[DRY RUN] SMS to %s: %s", to_number, message[:80])
            result = SMSResult(
                timestamp=now, to_number=to_number, delivered=True,
                message_sid="dry_run",
            )
            self._sms_log.append(result)
            return result

        client = self._get_client()
        if not client:
            return SMSResult(
                timestamp=now, to_number=to_number, delivered=False,
                error="No Twilio client available",
            )

        try:
            msg = client.messages.create(
                body=message,
                to=to_number,
                from_=self._from,
            )
            result = SMSResult(
                timestamp=now, to_number=to_number, delivered=True,
                message_sid=msg.sid,
            )
        except Exception as e:
            result = SMSResult(
                timestamp=now, to_number=to_number, delivered=False,
                error=str(e),
            )

        self._sms_log.append(result)
        return result

    # ── High-level eldercare interactions ──

    async def morning_checkin(self, profile) -> CallResult:
        """Morning check-in call with medication reminder."""
        name = profile.display_name
        messages = [
            f"Good morning, {name}. This is Cura.",
            f"How are you feeling today?",
        ]

        if hasattr(profile, 'medications') and profile.medications:
            med_names = [m.get("name", "medication") for m in profile.medications[:3]]
            if len(med_names) == 1:
                messages.append(f"Just a reminder — it's time for your {med_names[0]}.")
            else:
                meds = ', '.join(med_names[:-1]) + f' and {med_names[-1]}'
                messages.append(f"Just a reminder — it's time for your {meds}.")

        messages.append("Press 1 if you've taken your medications, or 2 if you need help.")

        phone = profile.emergency_contacts[0].get("phone", "") if profile.emergency_contacts else ""
        if not phone:
            phone = profile.primary_caregiver.get("phone", "")

        # Call the elder, not the caregiver
        elder_phone = getattr(profile, 'phone', phone)

        return await self.call(
            to_number=elder_phone,
            messages=messages,
            gather_response=True,
        )

    async def evening_checkin(self, profile) -> CallResult:
        """Evening check-in with daily summary."""
        name = profile.display_name
        messages = [
            f"Good evening, {name}. This is Cura.",
            f"I hope you had a good day.",
        ]

        if hasattr(profile, 'medications') and profile.medications:
            evening_meds = [m for m in profile.medications if 'evening' in m.get('time', '').lower() or 'pm' in m.get('time', '').lower()]
            if evening_meds:
                med_names = [m.get("name") for m in evening_meds]
                messages.append(f"Time for your evening medication — {', '.join(med_names)}.")

        messages.append("Is there anything you need before bed? Press 1 for yes, or 2 for no.")

        elder_phone = getattr(profile, 'phone', '')
        return await self.call(
            to_number=elder_phone,
            messages=messages,
            gather_response=True,
        )

    async def alert_caregiver(
        self,
        profile,
        alert_type: str,
        details: str,
    ) -> tuple[CallResult, SMSResult]:
        """Alert the primary caregiver about a concern.

        Both calls and texts — belt and suspenders for emergencies.
        """
        caregiver = profile.primary_caregiver
        caregiver_name = caregiver.get("name", "")
        caregiver_phone = caregiver.get("phone", "")
        elder_name = profile.display_name

        call_messages = [
            f"Hello {caregiver_name}, this is Cura, {elder_name}'s care companion.",
            f"I'm calling because {details}.",
            f"{elder_name} is at {profile.address}." if profile.address else "",
            "Please check in when you can. Press 1 to confirm you received this message.",
        ]
        call_messages = [m for m in call_messages if m]

        sms_text = (
            f"Cura alert for {elder_name}: {alert_type}. "
            f"{details}. "
            f"{'Address: ' + profile.address if profile.address else ''}"
        )

        call_result = await self.call(
            to_number=caregiver_phone,
            messages=call_messages,
            gather_response=True,
        )
        sms_result = await self.send_sms(caregiver_phone, sms_text)

        return call_result, sms_result

    async def crisis_alert(
        self,
        profile,
        crisis_type: str,
        details: str,
    ) -> list[tuple[str, Any]]:
        """Alert ALL emergency contacts about a crisis.

        Calls and texts every contact in parallel. This is the
        "Margaret fell at 2am" scenario.
        """
        results = []

        for contact in profile.emergency_contacts:
            phone = contact.get("phone", "")
            name = contact.get("name", "")
            if not phone:
                continue

            sms_text = (
                f"URGENT — Cura alert for {profile.display_name}: "
                f"{crisis_type}. {details}. "
                f"{'Address: ' + profile.address if profile.address else ''}"
            )

            sms_result = await self.send_sms(phone, sms_text)
            call_result = await self.call(
                to_number=phone,
                messages=[
                    f"Urgent message from Cura about {profile.display_name}.",
                    f"{details}.",
                    f"{profile.display_name} is at {profile.address}." if profile.address else "",
                    "Please respond as soon as possible.",
                ],
            )
            results.append((name, call_result, sms_result))

        return results

    @property
    def call_log(self) -> list[CallResult]:
        return list(self._call_log)

    @property
    def sms_log(self) -> list[SMSResult]:
        return list(self._sms_log)
