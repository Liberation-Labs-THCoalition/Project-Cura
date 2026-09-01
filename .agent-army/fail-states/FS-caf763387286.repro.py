"""FS-caf763387286 — CuraVoice.call() reports a failed Twilio call as answered.

The dry-run branch is the only branch any test executes. In the real branch,
`answered=True` is set the instant `client.calls.create()` returns — that call
returns as soon as Twilio has QUEUED the call, before the phone has rung. A call
that Twilio then reports as failed, busy, or no-answer is recorded as
CallResult(answered=True, error=""). Nothing later corrects it: /voice/status is
log-only.

For this household the phone ringing is the only evidence Cura works, and the
rural line is exactly the one that fails to connect. A call that never reached
him is indistinguishable, in Cura's own records, from one he answered.

The suite does not notice because no test ever constructs a Twilio client:
`client.calls.create` can be replaced with `None and client.calls.create` and
all 157 tests still pass.
"""
from __future__ import annotations

import asyncio

from cura.comms.voice import CuraVoice


class _FakeCall:
    """What twilio.rest.Client.calls.create() returns for a call that fails."""
    sid = "CAfake0000000000000000000000000000"
    status = "failed"
    error_code = 13224
    error_message = "Twilio could not find a valid destination"


class _FakeCalls:
    def __init__(self):
        self.created = []

    def create(self, **kwargs):
        self.created.append(kwargs)
        return _FakeCall()


class _FakeClient:
    def __init__(self):
        self.calls = _FakeCalls()


def _voice_with_fake_client():
    voice = CuraVoice(account_sid="ACfake", auth_token="tok",
                      from_number="+15550000000", dry_run=False)
    voice._client = _FakeClient()
    return voice


def test_a_failed_call_is_not_recorded_as_answered():
    voice = _voice_with_fake_client()
    result = asyncio.run(voice.call("+13075550143", ["Good morning, Bob."]))

    assert voice._client.calls.created, "no call was placed at all"
    assert not result.answered, (
        "Twilio reported status=%r for this call and CuraVoice recorded "
        "answered=True, error=%r. A call that never connected is logged as a "
        "check-in that was answered." % (_FakeCall.status, result.error)
    )


def test_a_failed_call_carries_its_error_into_the_record():
    voice = _voice_with_fake_client()
    result = asyncio.run(voice.call("+13075550143", ["Good morning, Bob."]))
    assert result.error, (
        "CallResult.error is empty for a call Twilio reported as %r — nothing "
        "downstream can tell the caregiver the call did not go through"
        % _FakeCall.status
    )
