"""A record of doses actually taken — per medication, per person, with times.

`CheckInResult.medication_confirmed` is a SINGLE BOOLEAN for an entire check-in.
Not per medication, no timestamp, no idea who said so. So when Margaret says "I
just took my pain pill" there is nowhere to put it, and `prn_status` — the guard
written to answer "may I take another one?" — has no input and has therefore had
zero call sites since it was written. The state the guard needs cannot be
expressed by the model that would supply it.

THE FIELD THAT MATTERS is `ever_recorded`. prn_status returns three states and
UNKNOWN never collapses into ALLOWED, because an unrecorded dose is
indistinguishable from no dose. That distinction only survives if something can
tell the difference between:

    an empty ledger because nobody in this house records doses
    an empty ledger because she has genuinely taken none today

A ledger that cannot tell those apart makes the guard's central safety property
decorative. So the ledger records whether it has EVER been written to, and that
is a fact about the household rather than about today.

WHO SAID SO is recorded too, and it is not decoration. The caregiver saying "I
gave her one at two" is good evidence. Cura inferring a dose from a check-in
answer is not, and speech recognition on an elderly voice with dementia is the
one source that must never silently become authority: a MISSED record permits a
double dose, a FALSE record withholds a painkiller from someone in pain, and
both directions do harm.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class Source:
    """Who says this dose happened. Ordered by how much weight it can bear."""
    CAREGIVER = "caregiver"      # a person who administers medication said so
    ELDER = "elder"              # the person taking it said so
    DEVICE = "device"            # a dispenser or sensor reported it
    INFERRED = "inferred"        # Cura concluded it. Never authoritative.


AUTHORITATIVE = frozenset({Source.CAREGIVER, Source.DEVICE})


@dataclass(frozen=True)
class Dose:
    medication: str
    taken_at: datetime
    source: str
    subject_id: str = ""
    note: str = ""

    @property
    def authoritative(self) -> bool:
        return self.source in AUTHORITATIVE


@dataclass
class DoseLedger:
    """Doses for one household. JSON on disk; Mnemosyne later.

    Thomas's call: ship with the simple ledger rather than block the household
    on an integration that does not exist yet. It is a file of timestamps and
    migrating it is easy.
    """
    path: Path | None = None
    doses: list[Dose] = field(default_factory=list)
    _ever_written: bool = False

    @property
    def ever_recorded(self) -> bool:
        """Whether this household records doses AT ALL.

        NOT `bool(self.doses)`. A ledger emptied by time still proves the
        household records; a ledger that has never been written proves nothing,
        and the difference is what keeps prn_status honest.
        """
        return self._ever_written

    def record(self, medication: str, taken_at: datetime, source: str,
               subject_id: str = "", note: str = "") -> Dose:
        if taken_at.tzinfo is None:
            taken_at = taken_at.replace(tzinfo=timezone.utc)
        d = Dose(medication=medication.strip(), taken_at=taken_at,
                 source=source, subject_id=subject_id, note=note)
        self.doses.append(d)
        # ONLY an authoritative write proves this household records doses.
        # Setting it on any write meant Cura's own guess established
        # "they log doses here", and then a guess that was correctly filtered
        # out of the evidence left prn_status reading "logs doses, none today"
        # -> ALLOWED. That is the double-dose path, opened by the filter that
        # exists to prevent it.
        if d.authoritative:
            self._ever_written = True
        self.save()
        return d

    def for_medication(self, medication: str, subject_id: str = "",
                       authoritative_only: bool = True) -> list[datetime]:
        """Dose times for one medication, oldest first.

        `authoritative_only` defaults TRUE. An inferred dose must not silently
        become the evidence a dosing decision rests on — prn_status treats a
        recorded dose as fact, so only sources that can bear that weight reach
        it by default.
        """
        name = medication.strip().lower()
        out = [d.taken_at for d in self.doses
               if d.medication.lower() == name
               and (not subject_id or d.subject_id == subject_id)
               and (d.authoritative or not authoritative_only)]
        return sorted(out)


    def unverified_since(self, medication: str, since: datetime,
                         subject_id: str = "") -> list[Dose]:
        """Non-authoritative doses recorded since `since`.

        Dropping these from the evidence loses information that matters. "I
        think she took one and cannot confirm it" is not "no record" — it is a
        reason to say I DO NOT KNOW rather than a reason to say yes.
        """
        name = medication.strip().lower()
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        return [d for d in self.doses
                if d.medication.lower() == name
                and not d.authoritative
                and (not subject_id or d.subject_id == subject_id)
                and d.taken_at >= since]

    # ---- persistence -------------------------------------------------
    def save(self) -> None:
        if not self.path:
            return
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ever_recorded": self._ever_written,
            "doses": [{**asdict(d), "taken_at": d.taken_at.isoformat()}
                      for d in self.doses],
        }
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        try:
            tmp.chmod(0o600)     # medication times are medical data
        except OSError:
            pass
        os.replace(tmp, p)

    @classmethod
    def load(cls, path) -> "DoseLedger":
        p = Path(path)
        led = cls(path=p)
        if not p.exists():
            return led
        try:
            data = json.loads(p.read_text())
        except (OSError, ValueError):
            # An unreadable ledger is NOT an empty one. Refusing to claim
            # ever_recorded here means prn_status answers UNKNOWN rather than
            # ALLOWED, which is the safe direction.
            return led
        led._ever_written = bool(data.get("ever_recorded"))
        for raw in data.get("doses", ()):
            try:
                led.doses.append(Dose(
                    medication=raw["medication"],
                    taken_at=datetime.fromisoformat(raw["taken_at"]),
                    source=raw.get("source", Source.INFERRED),
                    subject_id=raw.get("subject_id", ""),
                    note=raw.get("note", "")))
            except (KeyError, ValueError):
                continue
        return led


def prn_answer(medication: dict, ledger: DoseLedger, now: datetime,
               subject_id: str = "", tz=None):
    """Answer "may I take another one?" from the ledger. The wiring.

    prn_status has had ZERO call sites since it was written, because nothing
    could supply its dose history. This is that supply. Written in the same
    commit as the ledger deliberately: this codebase's most frequent defect is a
    correct half with nothing joined to it, and the guard against double-dosing
    is a poor place to add another.
    """
    from cura.pulse.medication import parse_medication, prn_status
    from cura.pulse.medication import PRNVerdict, PRNStatus
    med = parse_medication(medication)
    doses = ledger.for_medication(med.name, subject_id=subject_id)
    answer = prn_status(med, now, doses=doses,
                        ever_recorded=ledger.ever_recorded, tz=tz)

    # A weak signal we chose not to trust is still a signal. If the guard is
    # about to say ALLOWED while an unverified dose sits inside the interval
    # window, the honest answer is UNKNOWN.
    if answer.verdict is PRNVerdict.ALLOWED:
        window = timedelta(hours=med.min_interval_hours or 24)
        recent = ledger.unverified_since(med.name, now - window,
                                         subject_id=subject_id)
        if recent:
            return PRNStatus(
                PRNVerdict.UNKNOWN,
                f"I think you may have had {med.name} recently, but nobody "
                f"confirmed it, so I can't tell you it's safe. Please check "
                f"with your caregiver.",
                doses_today=answer.doses_today)
    return answer
