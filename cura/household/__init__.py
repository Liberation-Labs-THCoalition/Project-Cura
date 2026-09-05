"""The household — who Cura may reach, who Cura is caring for, and when.

ElderProfile models ONE person who is called on a schedule, with a caregiver
recorded as a contact dict. The first real household breaks that on the first
fact: the woman being cared for CANNOT ANSWER A PHONE, and the man Cura should
actually be talking to has never been called by it at all. He is, structurally,
an alarm recipient.

Three things this exists to express that ElderProfile cannot:

1. **The person Cura calls is not the person Cura cares for**, and may not be
   the same person twice in one household.
2. **Roles are not exclusive.** A sole caregiver is himself someone who needs
   care. Roles are DERIVED from who looks after whom and are never stored, so
   no two fields can disagree about what someone is.
3. **"May Cura call this person" is a recorded decision with four states**, not
   a boolean, and UNKNOWN is a real answer that schedules nothing and gets
   reported. Same shape as medication_slots -> silence + a question.

THE ONE RULE THIS MODULE EXISTS TO ENFORCE
------------------------------------------
Three independent designs for this model were reviewed, and all three had the
same safety flaw: the escalation path did not consult the calling permission.
Each separated "may Cura call this person for a check-in" from "may Cura call
this person for help", and each forgot to apply the permission to the second.
All three would have placed an emergency call to a woman who cannot answer a
phone.

That is a trap in the shape of the problem, not a mistake anyone made twice. So
there is exactly ONE permission function here -- `may_call(member, purpose)` --
and it is impossible to ask about check-ins without asking the same function
that answers about help. If the answer ever lives in two places they will drift,
and the drift is silent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable


class Reach(str, Enum):
    """Whether Cura may place a call to this person, as a recorded decision.

    UNKNOWN is not a default that means "probably fine". It means nobody has
    said, so nothing is scheduled and a human is asked. A boolean here would
    make "we never discussed it" indistinguishable from "no".
    """
    SCHEDULED = "scheduled"      # may be called on a schedule, and for help
    ON_REQUEST = "on_request"    # may be called FOR A REASON, never on a schedule
    NEVER = "never"              # must never be dialled, for any purpose
    UNKNOWN = "unknown"          # nobody has said; schedule nothing, report it


class Purpose(str, Enum):
    CHECKIN = "checkin"
    HELP = "help"


def may_call(member: "Member", purpose: Purpose) -> bool:
    """THE permission check. Every dial site asks this and nothing else.

    Deliberately one function taking a purpose, rather than two functions.
    Two functions is exactly how all three reviewed designs shipped an
    escalation path that ignored the permission.
    """
    if member.reach is Reach.SCHEDULED:
        return True
    if member.reach is Reach.ON_REQUEST:
        return purpose is Purpose.HELP
    return False        # NEVER and UNKNOWN are never dialled


def dialable(value: Any) -> bool:
    """Whether a number can actually be dialled.

    Emptiness alone was the old test, so the bare string "+" passed -- and "+"
    is what norm_phone("") used to return, so a skipped question became an
    emergency contact Cura believed it could reach.
    """
    digits = re.sub(r"\D", "", str(value or ""))
    return len(digits) >= 10 and not digits.lstrip("1").startswith(("0", "1"))


@dataclass(frozen=True)
class CheckIn:
    """One scheduled call: who is called, and who it is about.

    `to` and `about` are separate because the whole point is that they differ.
    Ray's evening call is TO Ray and ABOUT both of them.
    """
    slot: str                          # "morning" | "evening"
    about: tuple[str, ...] = ()        # member_ids; empty means "about the callee"


@dataclass
class Member:
    """One person in the household."""
    member_id: str
    name: str
    preferred_name: str = ""
    phone: str = ""
    reach: Reach = Reach.UNKNOWN
    cares_for: tuple[str, ...] = ()    # member_ids this person looks after
    checkins: tuple[CheckIn, ...] = ()
    medications: list[dict[str, Any]] = field(default_factory=list)
    address: str = ""

    def __post_init__(self) -> None:
        if self.checkins and not may_call(self, Purpose.CHECKIN):
            raise ValueError(
                f"{self.member_id!r} has scheduled check-ins but reach="
                f"{self.reach.value!r}; a schedule Cura may not act on is a "
                f"promise it cannot keep")

    @property
    def display_name(self) -> str:
        return self.preferred_name or self.name

    @property
    def reachable(self) -> bool:
        """Callable in principle: permitted for something AND has a number."""
        return dialable(self.phone) and (
            may_call(self, Purpose.HELP) or may_call(self, Purpose.CHECKIN))


@dataclass
class Household:
    """The people Cura serves, and nothing else.

    Small by construction. Thomas: "If someone has a dozen dedicated
    caregivers, what the hell do they need us for?" One to four people who
    actually show up -- not a care-team directory.
    """
    members: dict[str, Member] = field(default_factory=dict)
    _outside: tuple = ()      # monitoring service / dispatch line names

    def __post_init__(self) -> None:
        for mid, m in self.members.items():
            if m.member_id != mid:
                raise ValueError(f"member keyed {mid!r} but has id {m.member_id!r}")
            for other in m.cares_for:
                if other not in self.members:
                    raise ValueError(
                        f"{mid!r} cares_for {other!r}, who is not in the household")

    # ---- roles, always derived, never stored ---------------------------
    def is_caregiver(self, member_id: str) -> bool:
        return bool(self.members[member_id].cares_for)

    def is_cared_for(self, member_id: str) -> bool:
        return any(member_id in m.cares_for for m in self.members.values())

    def roles(self, member_id: str) -> set[str]:
        """Both, either, or neither. A sole caregiver is usually both.

        Derived so nothing can contradict anything else. Storing a role is how
        wizard.py ended up writing the same person into emergency_contacts[0]
        and primary_caregiver and letting them drift.
        """
        r = set()
        if self.is_caregiver(member_id):
            r.add("caregiver")
        if self.is_cared_for(member_id):
            r.add("cared_for")
        return r

    def caregivers_of(self, member_id: str) -> list[Member]:
        return [m for m in self.members.values() if member_id in m.cares_for]

    # ---- who may be called, for what -----------------------------------
    def callable_for(self, purpose: Purpose,
                     excluding: Iterable[str] = ()) -> list[Member]:
        """Everyone Cura may dial for this purpose, in a stable order.

        EXCLUSION IS BY PHONE NUMBER AS WELL AS BY ID. One reviewed design
        excluded the person who raised the alarm by member_id while dialling by
        number -- and its own notes said two people in a rural house share one
        landline. Cura would have rung the phone in the room where he was lying.
        """
        skip_ids = set(excluding)
        skip_numbers = {
            re.sub(r"\D", "", self.members[i].phone or "")
            for i in skip_ids if i in self.members
        } - {""}
        out = []
        for m in sorted(self.members.values(), key=lambda x: x.member_id):
            if m.member_id in skip_ids:
                continue
            if re.sub(r"\D", "", m.phone or "") in skip_numbers:
                continue
            if may_call(m, purpose) and dialable(m.phone):
                out.append(m)
        return out

    def responders_for(self, member_id: str) -> list[Member]:
        """Who to call when this person needs help. Their caregivers first."""
        helpers = self.callable_for(Purpose.HELP, excluding=(member_id,))
        carers = {m.member_id for m in self.caregivers_of(member_id)}
        return sorted(helpers, key=lambda m: (m.member_id not in carers, m.member_id))

    def scheduled_calls(self) -> list[tuple[Member, CheckIn]]:
        """Every call Cura should place, with the permission already applied.

        The permission is enforced HERE, inside the model, rather than at the
        scheduler -- so a future author who forgets to check cannot introduce a
        call that should not happen.
        """
        out = []
        for m in sorted(self.members.values(), key=lambda x: x.member_id):
            if not may_call(m, Purpose.CHECKIN) or not dialable(m.phone):
                continue
            for c in m.checkins:
                out.append((m, c))
        return out


    # ---- readiness, split by severity ----------------------------------
    def blocking_problems(self) -> list[str]:
        """Reasons Cura must NOT run at all. Empty means it may.

        Deliberately narrow. The old gate refused to start when "the person
        Cura calls has no phone number Cura can dial" -- which made the FIRST
        REAL HOUSEHOLD unconfigurable, because the woman being cared for cannot
        answer a phone. That is not an error; it is the fact the whole model
        exists to hold.

        What genuinely blocks is only this: nobody can be reached when someone
        needs help. Everything else is a gap to report, not a reason to leave a
        household with nothing.
        """
        problems = []
        if not self.members:
            return ["there is nobody in this household"]
        if not self.callable_for(Purpose.HELP):
            problems.append(
                "there is nobody Cura can call for help — every person is "
                "either marked never-to-call or has no number Cura can dial")
        for mid, m in sorted(self.members.items()):
            if m.checkins and not dialable(m.phone):
                problems.append(
                    f"{m.display_name} has check-ins scheduled but no number "
                    f"Cura can dial")
        return problems

    def reportable_gaps(self) -> list[str]:
        """Incomplete, but Cura still runs. Say these to the caregiver.

        Separate from blocking on purpose. A missing preference about a fifth
        person -- a physician, a neighbour -- must not take the household's
        phone service offline, which is what a single undifferentiated list
        does when every consumer treats non-empty as refuse-to-serve.
        """
        gaps = []
        for mid, m in sorted(self.members.items()):
            if m.reach is Reach.UNKNOWN:
                gaps.append(
                    f"nobody has said whether Cura may call {m.display_name}")
            elif m.reach is Reach.NEVER and self.is_cared_for(mid):
                if not self.caregivers_of(mid):
                    gaps.append(
                        f"{m.display_name} cannot be called and has nobody "
                        f"looking after them")
            if m.reach is not Reach.NEVER and m.phone and not dialable(m.phone):
                gaps.append(
                    f"{m.display_name}'s number is not one Cura can dial")
        # No rung outside this household. The research on emergency services
        # made this the sharpest gap we have: a licensed monitoring centre or
        # the county's 24/7 non-emergency dispatch line is the only rung that
        # does not depend on somebody in the house being able to answer, and
        # every medical-alert company that exists routes through one.
        if not self.outside_contacts():
            gaps.append(
                "there is no monitoring service or dispatch line on file, so "
                "if nobody in the household answers, the ladder ends there")

        # The sole-caregiver single point of failure, said out loud.
        for mid, m in sorted(self.members.items()):
            if not self.is_caregiver(mid):
                continue
            others = self.callable_for(Purpose.HELP, excluding=(mid,))
            if not others:
                gaps.append(
                    f"if {m.display_name} is the one who needs help, there is "
                    f"nobody else for Cura to call")
        return gaps

    def outside_contacts(self) -> list[str]:
        """Rungs that do not depend on someone in this house answering.

        Empty is the state the whole ladder exists to avoid and the one the
        first household is in today.
        """
        return list(self._outside)

    # ---- the projection ------------------------------------------------
    def profile_for(self, member_id: str):
        """One member, shaped as the ElderProfile the rest of Cura expects.

        This is the migration path. voice.py, escalation.py, checkin_composer.py
        and daily_enrichments.py read a profile and are correct for a household
        WITHOUT ANY EDITS, because they read the projection instead of the
        model.

        `phone` is BLANK when Cura may not call this person, while the real
        number stays on the Member as a fact. Every dial site reads
        profile.phone, so a person marked never-to-call cannot be dialled by
        code that has not been taught about reach.
        """
        from cura.pulse.eldercare_pulse import ElderProfile
        m = self.members[member_id]
        responders = self.responders_for(member_id)
        primary = responders[0] if responders else None
        return ElderProfile(
            name=m.name,
            preferred_name=m.preferred_name,
            phone=m.phone if may_call(m, Purpose.CHECKIN) else "",
            medications=list(m.medications),
            emergency_contacts=[
                {"name": r.display_name, "phone": r.phone,
                 "relation": "caregiver" if member_id in r.cares_for else "contact"}
                for r in responders
            ],
            primary_caregiver=({"name": primary.display_name,
                                "phone": primary.phone} if primary else {}),
            address=m.address,
        )

    # ---- serialisation --------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict) -> "Household":
        # _outside had no writer anywhere, so outside_contacts() was
        # constant-empty and reportable_gaps() emitted "there is no monitoring
        # service or dispatch line on file" for EVERY household including ones
        # that had one. A warning that is always true carries no information,
        # which is the same defect as a check that cannot fail.
        outside = tuple(
            (data.get(k) or {}).get("name") or k
            for k in ("dispatch_line", "monitoring_service", "physician")
            if (data.get(k) or {}).get("phone"))
        members = {}
        for raw in data.get("household", {}).get("members", []):
            mid = raw["member_id"]
            members[mid] = Member(
                member_id=mid,
                name=raw.get("name", ""),
                preferred_name=raw.get("preferred_name", ""),
                phone=raw.get("phone", ""),
                reach=Reach(raw.get("reach", "unknown")),
                cares_for=tuple(raw.get("cares_for", ())),
                checkins=tuple(CheckIn(slot=c["slot"],
                                       about=tuple(c.get("about", ())))
                               for c in raw.get("checkins", ())),
                medications=list(raw.get("medications", ())),
                address=raw.get("address", ""),
            )
        return cls(members=members, _outside=outside)
