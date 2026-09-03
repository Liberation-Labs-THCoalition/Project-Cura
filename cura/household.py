"""The household — who Cura may reach, who Cura is caring for, and when.

ElderProfile (cura/pulse/eldercare_pulse.py:99) models one person who is
simultaneously the listener, the subject of care, the owner of the medication
list and the only phone number. In the first real household those are two
different people:

    Ray  -- seventies, failing eyesight, sole caregiver. Answers the phone.
    Margaret -- late-stage dementia. CANNOT answer a phone.

Every line Cura speaks today is second-person to the medication owner
("It's time for your Donepezil", eldercare_pulse.py:243). Spoken to Ray that is
not a wording error, it is a claim about whose body the drug enters.

So the model separates four things the old one welded together:

  1. LISTENER   -- who is on the line.
  2. SUBJECT    -- who the sentence is about.
  3. RESPONDERS -- who Cura summons when the listener needs help.
                   Never the listener. escalation_readiness (escalation.py:57)
                   never compares those two, so the one configuration where
                   escalation is useless is the one it reports as ready.
  4. CADENCE    -- how often, per person, including NONE.

The governing rule, in this file's terms:

    NOT BEING CALLED IS A RECORDED DECISION, NOT A MISSING PHONE NUMBER.

Margaret has no cadence because someone said she must not be called, and
`Initiative.NEVER` is where that sentence is stored. An empty `checkins` list
that merely means "nobody filled this in" is indistinguishable from a person
Cura has been told to leave alone -- and the two have opposite failure modes.

WHAT LIVES HERE AND WHAT DOES NOT.  This file is ADDRESSING: who exists, how to
reach them, when. It is small, static, and changes when the household changes.
KNOWLEDGE -- current medications, dose events, care considerations, what changed
this week -- lives behind `CareRecord`, which Mnemosyne will implement. The one
part of today's config that changes on a doctor's visit is `medications`, and it
is the one part that does not belong in a config file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Iterable, Iterator, Protocol

ALL_DAYS = frozenset(range(7))          # 0 = Monday .. 6 = Sunday


# --------------------------------------------------------------- initiative

class Initiative(str, Enum):
    """Whether Cura may START a conversation with this person.

    This is the field that makes stage 1 -> 2 -> 3 additive rather than a
    rewrite. Margaret moves NEVER -> OPPORTUNISTIC and nothing else changes.
    """

    SCHEDULED = "scheduled"
    """Cura places calls to this person on their own cadence."""

    OPPORTUNISTIC = "opportunistic"
    """Cura may speak to this person only on a call that already exists --
    handed the phone, or picking up an inbound one. Cura never dials them.
    A call she cannot process is a distress event, so 'may be spoken to' and
    'may be rung' have to be separately expressible."""

    NEVER = "never"
    """Cura must not initiate contact, and must not be routed into a
    conversation with this person. A recorded decision."""


class Channel(str, Enum):
    VOICE = "voice"
    SMS = "sms"


def digits_of(number: str) -> str:
    """The comparable part of a phone number.

    Twilio's `From` arrives E.164; a config may hold anything a human typed.
    Matching on the raw string means the caregiver calls in and is not
    recognised, which is the state webhook.py:184 is stuck in today.
    """
    return re.sub(r"\D", "", str(number or "")).lstrip("1")


def dialable(number: str) -> bool:
    """Whether a call can actually be placed to this. Same rule as
    cura.comms.escalation._dialable -- deliberately duplicated nowhere:
    this delegates so the two cannot drift."""
    from cura.comms.escalation import _dialable
    return _dialable(number)


# ------------------------------------------------------------------ cadence

@dataclass(frozen=True)
class Checkin:
    """One recurring conversation Cura initiates.

    Replaces `morning_time`/`evening_time` (eldercare_pulse.py:103-104), two
    ints with no off value -- 0 is midnight, not silence -- which became two
    unconditional cron jobs at __main__.py:416-417. Zero check-ins, one
    check-in, three check-ins and weekly are all expressible here and none of
    them were expressible there.

    `about` is the half that fixes the register. A check-in is TO the person
    holding this object and ABOUT the people named here. Ray's morning call is
    about Margaret; his weekly call is about himself. Nothing downstream has to
    guess.
    """
    slot: str                       # "morning" | "evening": which composer recipe
    hour: int
    minute: int = 0
    days: frozenset[int] = ALL_DAYS
    about: tuple[str, ...] = ()     # person_ids this call enquires after
    kind: str = "wellbeing"         # wellbeing | medication | caregiver_support
    label: str = ""                 # what the household calls it, for the log

    def __post_init__(self) -> None:
        if self.slot not in ("morning", "evening"):
            raise ValueError(
                f"slot {self.slot!r}: the composer has exactly two recipes "
                "(compose_morning, compose_evening). A third register needs a "
                "third recipe, not a new label.")
        if not 0 <= self.hour <= 23 or not 0 <= self.minute <= 59:
            raise ValueError(f"{self.hour}:{self.minute} is not a clock time")

    @property
    def is_weekly(self) -> bool:
        return len(self.days) < 7


# ------------------------------------------------------------------- person

@dataclass
class Person:
    """One member of the household. Roles are not fields, they are relations.

    An earlier sketch carried `role: "elder" | "caregiver"`. That cannot say
    what this household is -- Ray is both, and the primary contact will OFTEN
    be a caregiver who also needs care. A stored role can also disagree with
    the relations around it, and a role that contradicts the graph is exactly
    the confident wrong answer this codebase keeps producing.

    So: `cares_for` is the only place a caregiving relation is written down,
    and `is_caregiver` / `is_cared_for` are derived from it and cannot drift.
    """
    person_id: str                     # stable slug, NEVER the display name
    name: str
    preferred_name: str = ""
    numbers: tuple[str, ...] = ()      # every number that is this person
    initiative: Initiative = Initiative.NEVER
    checkins: tuple[Checkin, ...] = ()
    cares_for: tuple[str, ...] = ()    # person_ids this person looks after
    responders: tuple[str, ...] = ()   # who to summon when THIS person needs help
    timezone: str = ""                 # "" = use the household's
    address: str = ""                  # "" = use the household's
    can_receive_sms: bool = True

    def __post_init__(self) -> None:
        if self.initiative is Initiative.SCHEDULED and not self.dialable_numbers:
            raise ValueError(
                f"{self.person_id}: SCHEDULED with no dialable number. A "
                "cadence Cura cannot dial is a cadence that silently never "
                "fires.")
        if self.initiative is not Initiative.SCHEDULED and self.checkins:
            raise ValueError(
                f"{self.person_id}: has check-ins but initiative is "
                f"{self.initiative.value}. Two halves that disagree; the "
                "scheduler would believe one and the greeting the other.")

    # person_id is the identity everywhere. display_name is for speaking only.
    @property
    def display_name(self) -> str:
        return self.preferred_name or self.name

    @property
    def dialable_numbers(self) -> tuple[str, ...]:
        return tuple(n for n in self.numbers if dialable(n))

    @property
    def phone(self) -> str:
        """The first dialable number, or "". Named `phone` so a Person can be
        passed anywhere ElderProfile.phone was read."""
        nums = self.dialable_numbers
        return nums[0] if nums else ""

    @property
    def is_caregiver(self) -> bool:
        return bool(self.cares_for)

    @property
    def answers_the_phone(self) -> bool:
        return self.initiative is Initiative.SCHEDULED and bool(self.phone)

    def owns_number(self, number: str) -> bool:
        d = digits_of(number)
        return bool(d) and any(digits_of(n) == d for n in self.numbers)


# ---------------------------------------------------------------- addressing

@dataclass(frozen=True)
class Addressing:
    """Who is being spoken to, and who is being spoken about.

    Every spoken line needs both, and the old model had one name doing both
    jobs -- which is how `build_inbound_greeting(elder_name)` (responder.py:182)
    greets Ray as "Margaret", and how `generate_medication_reminder`
    (eldercare_pulse.py:227) tells him to swallow her Donepezil.

    Passing this per turn rather than per process is also what makes stage 3
    an addition: Ray hands Margaret the phone, the listener is rebound, and no
    scheduling, config or model changes.
    """
    listener: Person
    subject: Person

    @property
    def is_self(self) -> bool:
        return self.listener.person_id == self.subject.person_id

    @property
    def possessive(self) -> str:
        """"your" or "Margaret's" -- the whole administering/self distinction
        in one token."""
        return "your" if self.is_self else f"{self.subject.display_name}'s"

    @property
    def pronoun_or_name(self) -> str:
        return "you" if self.is_self else self.subject.display_name

    def medication_line(self, med_names: list[str]) -> str:
        """The register-correct medication sentence, or "" when none are due.

        Second person is a prompt to TAKE. Third person is a prompt to
        ADMINISTER. eldercare_pulse.py:243 can only build the first, so there
        is no way to say the only sentence this household needs.
        """
        if not med_names:
            return ""
        if len(med_names) == 1:
            names = med_names[0]
        else:
            names = f"{', '.join(med_names[:-1])} and {med_names[-1]}"
        if self.is_self:
            return f"It's time for your {names}."
        return f"It's about time for {self.subject.display_name}'s {names}."


# ------------------------------------------------------------ what happened

@dataclass(frozen=True)
class Concern:
    """Something Cura noticed about a person, phrased so ANY listener can hear it.

    wearable.py:111-113 emits "Your heart rate has been higher than usual" and
    checkin_composer.py:109 splices it into whoever's check-in. The moment her
    band feeds his call, Cura asks Ray whether HE is short of breath, from her
    SpO2. Observation and listener are welded together in the string.

    Here the text is third-person and subject-tagged, so the same Concern can be
    rendered to Ray as "Margaret's oxygen read 89% at four this morning" and, if
    she is ever the listener, to her as "your oxygen...". This is the whole of
    stage 2: sensors produce Concerns about Margaret, and Ray's existing
    check-in renders them. No new job, no new model.
    """
    about: str                        # person_id
    text: str                         # third-person, no "your"
    severity: float                   # 0-1
    at: datetime
    source: str = "sensor"            # sensor | voice | interaction | caregiver


@dataclass(frozen=True)
class DoseEvent:
    """One (drug, time, who gave it, who took it) fact.

    CheckInResult.medication_confirmed (eldercare_pulse.py:132) is ONE boolean
    for a whole call, and record_checkin (:163) only ever writes True -- I ran
    it: a CheckInResult with medication_confirmed=False leaves
    medication_adherence == {}. "She refused it", "he forgot" and "nobody
    asked" are all stored as nothing, which is the exact state medication.py
    was rewritten to stop collapsing.

    `given_by` is what makes this household representable at all: Ray confirms,
    Margaret takes. `at` is the DOSE's clock time, not the call's.
    """
    subject: str                      # person_id who took it
    medication: str
    at: datetime
    given_by: str = ""                # person_id who administered; "" = unknown
    taken: bool | None = None         # True/False/None -- None is "not asked"
    source: str = "checkin"


# ------------------------------------------------------- the knowledge layer

class CareRecord(Protocol):
    """The read interface Mnemosyne will implement. Cura asks; Cura does not store.

    Everything here changes without the household changing: a new prescription,
    a dose given at 9:15, a note that she does better after breakfast. Today the
    only way to change `medications` is `cura setup --again`, which unlinks the
    whole progress file (wizard.py:300) and re-asks every question.

    `dose_log_is_authoritative` is the single most dangerous method in this
    protocol and the reason it is a method rather than a flag on a config.
    prn_status (medication.py:302) returns ALLOWED on an empty dose list when
    `ever_recorded` is True and UNKNOWN when it is not -- and there is no writer
    for that field anywhere in the repo. A future caller that passes True
    because "we have a dose log now" turns every UNLOGGED dose into a green
    light on an opioid. The default here is False, and it stays False until a
    household can demonstrate that every dose is actually written down.
    """

    def medications(self, person_id: str) -> list[dict[str, Any]]: ...

    def doses(self, person_id: str, medication: str,
              since: datetime) -> list[DoseEvent]: ...

    def dose_log_is_authoritative(self, person_id: str) -> bool: ...

    def considerations(self, person_id: str) -> list[str]:
        """Per-household conversation guidance, shown to caregivers, not spoken.
        This is where "bespoke" lives -- as data, not as a fork."""


class ConfigCareRecord:
    """The transition-period CareRecord: reads what setup already wrote.

    Answers `medications` from the config so nothing regresses, and answers
    `dose_log_is_authoritative` False and `doses` empty -- because there is no
    dose store, and saying otherwise is the failure above. So every PRN question
    resolves to UNKNOWN and defers to a human, which is correct and honest until
    Mnemosyne is wired in.
    """

    def __init__(self, by_person: dict[str, list[dict[str, Any]]]) -> None:
        self._meds = by_person

    def medications(self, person_id: str) -> list[dict[str, Any]]:
        return list(self._meds.get(person_id, []))

    def doses(self, person_id: str, medication: str,
              since: datetime) -> list[DoseEvent]:
        return []

    def dose_log_is_authoritative(self, person_id: str) -> bool:
        return False

    def considerations(self, person_id: str) -> list[str]:
        return []


# ---------------------------------------------------------------- household

@dataclass
class Household:
    """One to four people who actually show up, and the wiring between them.

    Not a care-team directory. If someone has a dozen dedicated caregivers they
    do not need us; the network is small by construction and this type does not
    try to be an org chart.

    One household, one file. Today the filename is derived from
    preferred_name (wizard.py:403), so a second person makes a second file with
    nothing linking them -- and _default_config_path (__main__.py:236-249)
    returns None once more than one exists. I ran it: two configs -> None, and
    `cura rehearse` then tells a household that set Cura up twice that "Cura
    isn't set up yet".
    """
    household_id: str
    people: tuple[Person, ...]
    timezone: str                       # required: no silent America/New_York
    address: str = ""
    care_record: CareRecord | None = None

    # ------------------------------------------------------------ lookups
    def __iter__(self) -> Iterator[Person]:
        return iter(self.people)

    def person(self, person_id: str) -> Person | None:
        return next((p for p in self.people if p.person_id == person_id), None)

    def person_for_number(self, number: str) -> Person | None:
        """Who is on the line. Returns None for a number nobody claims.

        None is the point. Cura holds the caller's number on every inbound POST
        and throws it away (webhook.py:195), so an unknown caller is greeted by
        the elder's name. A stranger must be greeted as a stranger.
        """
        return next((p for p in self.people if p.owns_number(number)), None)

    def tz_for(self, person_id: str) -> str:
        p = self.person(person_id)
        return (p.timezone if p and p.timezone else self.timezone)

    def address_for(self, person_id: str) -> str:
        p = self.person(person_id)
        return (p.address if p and p.address else self.address)

    # ------------------------------------------------------------- cadence
    def scheduled_jobs(self) -> list[tuple[Person, Checkin]]:
        """Every call Cura will place, as (listener, checkin).

        The scheduler builds jobs from THIS and nothing else, so "she is never
        called" is enforced in one readable place rather than by the absence of
        a line in __main__.
        """
        out: list[tuple[Person, Checkin]] = []
        for p in self.people:
            if p.initiative is not Initiative.SCHEDULED:
                continue
            for c in p.checkins:
                out.append((p, c))
        return out

    def addressings(self, listener: Person, checkin: Checkin) -> list[Addressing]:
        """The (listener, subject) pairs this one call has to speak in."""
        subjects = [self.person(s) for s in checkin.about]
        return [Addressing(listener, s) for s in subjects if s is not None]

    # ---------------------------------------------------------- escalation
    def responders_for(self, person_id: str) -> list[Person]:
        """Who Cura summons when THIS person needs help -- never that person.

        build_escalation (escalation.py:82) fires crisis_alert at
        profile.emergency_contacts, which in this household is Ray. I ran it in
        dry-run: Ray asks Cura for help and Cura texts and calls Ray's own phone
        saying "Urgent message from Cura about Margaret ... Margaret is at Rural
        Route 2". The loop closes on the man who asked, and reports success.
        """
        p = self.person(person_id)
        if p is None:
            return []
        named = [self.person(r) for r in p.responders]
        chosen = [r for r in named if r is not None]
        if not chosen:
            # Anyone who looks after them, then anyone else reachable.
            chosen = [o for o in self.people
                      if person_id in o.cares_for and o.person_id != person_id]
        if not chosen:
            chosen = [o for o in self.people if o.person_id != person_id]
        return [r for r in chosen
                if r.person_id != person_id and r.dialable_numbers]

    def readiness_problems(self) -> list[str]:
        """Reasons Cura must refuse to serve this household, in plain words.

        Generalises escalation_readiness (escalation.py:50) from "the profile
        subject must be dialable" to "everyone Cura can hear a help request
        from must have SOMEONE ELSE to summon". That relaxation is what makes
        this household configurable at all -- Margaret has no number by design
        -- and the added clause is what stops the current config passing while
        wiring Ray's emergencies to Ray.
        """
        problems: list[str] = []
        if not self.people:
            problems.append("nobody is set up in this household")
        if not self.timezone:
            problems.append(
                "no timezone — Cura would call at the server's hour, not yours")
        reachable = [p for p in self.people if p.dialable_numbers]
        if not reachable:
            problems.append(
                "nobody has a phone number Cura can dial — no one can be reached")
        for p in self.people:
            if p.initiative is Initiative.SCHEDULED and not p.checkins:
                problems.append(
                    f"{p.display_name} is set to be called but has no check-in "
                    f"times — Cura would never ring")
            for c in p.checkins:
                for sid in c.about:
                    if self.person(sid) is None:
                        problems.append(
                            f"{p.display_name}'s {c.slot} check-in is about "
                            f"{sid!r}, who is not in this household")
        return problems

    def escalation_gaps(self) -> list[str]:
        """People Cura cannot summon help FOR. Not blocking. Never silent.

        Deliberately NOT a readiness failure, and this is the load-bearing
        decision in the file. A sole caregiver with nobody behind him is the
        first real deployment, and a gate that refuses it forbids the only
        household we have. escalation_readiness (escalation.py:63) refuses on
        exactly this and is why Thomas's household cannot be configured at all.

        What it changes instead is what Cura may SAY. _promise_help
        (responder.py:52) already has the honest branch -- "I can't reach anyone
        for you myself right now, please hang up and dial nine one one, I'm
        going to stay on the line" -- and it is reached when on_help_requested
        is None. So a person with a gap gets a responder built with no callback
        FOR THEM, and hears the truth rather than "I'm contacting your family
        right now" (responder.py:224), which today is said unconditionally and
        contacts nobody.
        """
        out = []
        for p in self.people:
            if p.initiative is Initiative.NEVER and not p.numbers:
                continue        # cannot ask, so nothing to promise
            if not self.responders_for(p.person_id):
                out.append(
                    f"if {p.display_name} asks Cura for help there is nobody "
                    f"else to call — Cura will say so rather than promise")
        return out

    def can_escalate_for(self, person_id: str) -> bool:
        """Whether Cura may promise this person that help is coming."""
        return bool(self.responders_for(person_id))

    def unresolved(self) -> list[str]:
        """What nobody has said yet. Not blocking, but never silent.

        Distinct from readiness_problems on purpose: these do not stop Cura
        running, and if they are not printed at the end of setup the household
        is told "All set" over them. That is the same trust failure
        unknown_timing_medications (eldercare_pulse.py:75) was written to name.
        """
        out: list[str] = []
        for p in self.people:
            if p.initiative is Initiative.NEVER and not p.cares_for:
                if not any(p.person_id in o.cares_for for o in self.people):
                    out.append(
                        f"{p.display_name} is never contacted and nobody is "
                        f"recorded as looking after them")
            if p.initiative is Initiative.SCHEDULED and not any(
                    c.kind == "caregiver_support" for c in p.checkins):
                if p.is_caregiver:
                    out.append(
                        f"nothing asks after {p.display_name}, who is looking "
                        f"after someone else")
        if not self.address:
            out.append("no address — an emergency alert would say where nobody")
        return out

    # ------------------------------------------------- backward compatibility
    def to_legacy_profile(self, person_id: str):
        """An ElderProfile for one person, so today's consumers keep working.

        This is the bridge that lets the household model land while
        CheckinComposer, EldercarePulseConfig, CuraVoice.crisis_alert and both
        wizards read exactly what they read now. It is deliberately lossy and
        the losses are the point: everything it drops is a state ElderProfile
        cannot express.
        """
        from cura.pulse.eldercare_pulse import ElderProfile
        p = self.person(person_id)
        if p is None:
            raise KeyError(person_id)
        meds = (self.care_record.medications(person_id)
                if self.care_record else [])
        responders = self.responders_for(person_id)
        morning = next((c for c in p.checkins if c.slot == "morning"), None)
        evening = next((c for c in p.checkins if c.slot == "evening"), None)
        primary = responders[0] if responders else None
        return ElderProfile(
            name=p.name,
            preferred_name=p.preferred_name,
            phone=p.phone,
            medications=meds,
            emergency_contacts=[{"name": r.display_name, "phone": r.phone,
                                 "relation": "caregiver"} for r in responders],
            primary_caregiver=({"name": primary.display_name,
                                "phone": primary.phone} if primary else {}),
            address=self.address_for(person_id),
            morning_time=morning.hour if morning else 8,
            evening_time=evening.hour if evening else 20,
            timezone=self.tz_for(person_id),
        )


# -------------------------------------------------------------- the loader

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-") or "person"


def household_from_config(data: dict[str, Any]) -> Household:
    """Build a Household from either the new `people` block or today's flat config.

    write_config merges rather than replaces (wizard.py:224) and every reader
    uses data.get with a default (__main__.py:211-219, 262-270, 339-349;
    preview.py:16-24), so a new top-level `people` block can be written by setup
    today and stay invisible to all five readers and all 333 tests.

    The legacy branch is not a guess about intent, it is a transcription of what
    the old fields MEANT: one dialable subject who is called twice a day, plus
    one contact who is only ever shouted at. Where the old config cannot say
    something, this refuses to invent it.
    """
    tz = data.get("timezone") or ""
    address = data.get("address", "")

    if data.get("people"):
        people = []
        for raw in data["people"]:
            checkins = tuple(
                Checkin(slot=c["slot"], hour=int(c["hour"]),
                        minute=int(c.get("minute", 0)),
                        days=frozenset(c.get("days", ALL_DAYS)),
                        about=tuple(c.get("about", ())),
                        kind=c.get("kind", "wellbeing"),
                        label=c.get("label", ""))
                for c in raw.get("checkins", []))
            people.append(Person(
                person_id=raw["person_id"], name=raw.get("name", ""),
                preferred_name=raw.get("preferred_name", ""),
                numbers=tuple(raw.get("numbers", ())),
                initiative=Initiative(raw.get("initiative", "never")),
                checkins=checkins,
                cares_for=tuple(raw.get("cares_for", ())),
                responders=tuple(raw.get("responders", ())),
                timezone=raw.get("timezone", ""),
                address=raw.get("address", ""),
            ))
        meds = {p.person_id: data.get("medications_by_person", {}).get(p.person_id, [])
                for p in people}
        if data.get("medications") and not any(meds.values()):
            # Legacy single list: it belongs to whoever the old config was about.
            subject = data.get("medications_for") or people[0].person_id
            meds[subject] = data["medications"]
        return Household(
            household_id=data.get("household_id") or _slug(data.get("name", "")),
            people=tuple(people), timezone=tz, address=address,
            care_record=ConfigCareRecord(meds))

    # ---- legacy: one subject, one contact ---------------------------------
    elder_id = _slug(data.get("preferred_name") or data.get("name") or "elder")
    cg = data.get("primary_caregiver") or {}
    contacts = list(data.get("emergency_contacts") or [])
    cg_id = _slug(cg.get("name") or (contacts[0].get("name") if contacts else "")
                  or "caregiver")
    if cg_id == elder_id:
        cg_id = f"{cg_id}-caregiver"

    elder = Person(
        person_id=elder_id, name=data.get("name", ""),
        preferred_name=data.get("preferred_name", ""),
        numbers=tuple(n for n in [data.get("phone", "")] if n),
        initiative=(Initiative.SCHEDULED if dialable(data.get("phone", ""))
                    else Initiative.NEVER),
        checkins=((Checkin("morning", int(data.get("morning_time", 8)),
                           about=(elder_id,), kind="medication"),
                   Checkin("evening", int(data.get("evening_time", 20)),
                           about=(elder_id,)))
                  if dialable(data.get("phone", "")) else ()),
        responders=(cg_id,),
    )
    others = []
    seen = {elder_id}
    for c in ([cg] if cg.get("phone") else []) + contacts:
        pid = _slug(c.get("name") or "contact")
        if pid == elder_id:
            pid = f"{pid}-caregiver"
        if pid in seen:
            continue
        seen.add(pid)
        others.append(Person(
            person_id=pid, name=c.get("name", ""), preferred_name=c.get("name", ""),
            numbers=tuple(n for n in [c.get("phone", "")] if n),
            initiative=Initiative.OPPORTUNISTIC,   # reachable, never dialled on a cadence
            cares_for=(elder_id,),
            responders=(),
        ))
    return Household(
        household_id=elder_id, people=(elder, *others), timezone=tz,
        address=address,
        care_record=ConfigCareRecord({elder_id: data.get("medications", [])}))
