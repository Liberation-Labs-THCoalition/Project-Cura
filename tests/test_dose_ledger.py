"""The dose ledger — what makes prn_status able to answer anything.

CheckInResult.medication_confirmed is a SINGLE BOOLEAN for a whole check-in, so
"I just took my pain pill" had nowhere to go, and prn_status has had zero call
sites since it was written. The state the guard needs could not be expressed by
the model that would supply it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cura.pulse.dose_ledger import DoseLedger, Source, prn_answer
from cura.pulse.medication import PRNVerdict

NOW = datetime(2026, 9, 4, 20, 0, tzinfo=timezone.utc)
OXY = {"name": "oxycodone",
       "time": "as needed, every 4-6 hours, no more than 4 in 24 hours"}


class TestEverRecordedIsAboutTheHouseholdNotToday:
    def test_a_fresh_ledger_has_never_recorded(self):
        assert DoseLedger().ever_recorded is False

    def test_an_authoritative_write_establishes_it(self):
        led = DoseLedger()
        led.record("oxycodone", NOW - timedelta(hours=6), Source.CAREGIVER)
        assert led.ever_recorded is True

    def test_it_survives_the_doses_ageing_out(self):
        """A ledger emptied by time still proves the household records.
        bool(doses) would lose that and send the guard to UNKNOWN forever."""
        led = DoseLedger()
        led.record("oxycodone", NOW - timedelta(days=40), Source.CAREGIVER)
        assert led.ever_recorded is True
        assert led.for_medication("oxycodone")


class TestAnInferredDoseIsNotEvidence:
    """The double-dose path, opened by the filter that exists to prevent it.

    Cura infers a dose ten minutes ago. for_medication correctly refuses to
    treat it as authoritative — but record() set ever_recorded anyway, so
    prn_status read "this household logs doses, none today" and returned
    ALLOWED. Filtering the weak evidence out lost the very information that
    should have produced caution.
    """

    def test_an_inferred_dose_does_not_establish_ever_recorded(self):
        led = DoseLedger()
        led.record("oxycodone", NOW - timedelta(minutes=10), Source.INFERRED)
        assert led.ever_recorded is False, \
            "Cura's own guess established that the household records doses"

    def test_an_inferred_dose_does_not_permit_another(self):
        led = DoseLedger()
        led.record("oxycodone", NOW - timedelta(minutes=10), Source.INFERRED)
        s = prn_answer(OXY, led, NOW)
        assert s.verdict is PRNVerdict.UNKNOWN
        assert s.safe_to_take is False

    def test_an_unverified_dose_blocks_an_otherwise_allowed_answer(self):
        """Caregiver dose six hours ago would be ALLOWED; an unconfirmed one
        ten minutes ago must pull it back to UNKNOWN."""
        led = DoseLedger()
        led.record("oxycodone", NOW - timedelta(hours=6), Source.CAREGIVER)
        assert prn_answer(OXY, led, NOW).verdict is PRNVerdict.ALLOWED
        led.record("oxycodone", NOW - timedelta(minutes=10), Source.ELDER)
        assert prn_answer(OXY, led, NOW).verdict is PRNVerdict.UNKNOWN

    def test_an_old_unverified_dose_does_not_block_forever(self):
        led = DoseLedger()
        led.record("oxycodone", NOW - timedelta(hours=30), Source.INFERRED)
        led.record("oxycodone", NOW - timedelta(hours=8), Source.CAREGIVER)
        assert prn_answer(OXY, led, NOW).verdict is PRNVerdict.ALLOWED

    def test_a_device_report_is_authoritative(self):
        led = DoseLedger()
        led.record("oxycodone", NOW - timedelta(minutes=30), Source.DEVICE)
        assert led.ever_recorded is True
        assert prn_answer(OXY, led, NOW).verdict is PRNVerdict.TOO_SOON


class TestTheGuardNowAnswers:
    def test_a_confirmed_dose_thirty_minutes_ago_is_too_soon(self):
        led = DoseLedger()
        led.record("oxycodone", NOW - timedelta(minutes=30), Source.CAREGIVER)
        s = prn_answer(OXY, led, NOW)
        assert s.verdict is PRNVerdict.TOO_SOON and s.safe_to_take is False

    def test_a_confirmed_dose_six_hours_ago_is_allowed(self):
        led = DoseLedger()
        led.record("oxycodone", NOW - timedelta(hours=6), Source.CAREGIVER)
        assert prn_answer(OXY, led, NOW).safe_to_take is True

    def test_four_confirmed_doses_hit_the_daily_ceiling(self):
        led = DoseLedger()
        for h in (20, 14, 9, 5):
            led.record("oxycodone", NOW - timedelta(hours=h), Source.CAREGIVER)
        assert prn_answer(OXY, led, NOW).verdict is PRNVerdict.AT_DAILY_MAX

    def test_doses_are_kept_per_medication(self):
        led = DoseLedger()
        led.record("tylenol", NOW - timedelta(minutes=5), Source.CAREGIVER)
        assert prn_answer(OXY, led, NOW).doses_today == 0


class TestPersistence:
    def test_a_ledger_round_trips(self, tmp_path):
        p = tmp_path / "doses.json"
        led = DoseLedger(path=p)
        led.record("oxycodone", NOW - timedelta(hours=2), Source.CAREGIVER)
        back = DoseLedger.load(p)
        assert back.ever_recorded is True
        assert back.for_medication("oxycodone") == led.for_medication("oxycodone")

    def test_the_file_is_private(self, tmp_path):
        p = tmp_path / "doses.json"
        DoseLedger(path=p).record("oxycodone", NOW, Source.CAREGIVER)
        assert oct(p.stat().st_mode & 0o777) == "0o600"

    def test_an_unreadable_ledger_does_not_claim_ever_recorded(self, tmp_path):
        """The safe direction: UNKNOWN rather than ALLOWED."""
        p = tmp_path / "doses.json"
        p.write_text("{ this is not json")
        assert DoseLedger.load(p).ever_recorded is False

    def test_a_missing_ledger_is_not_an_empty_one(self, tmp_path):
        assert DoseLedger.load(tmp_path / "nope.json").ever_recorded is False
