"""Tests for cura.household — the one permission function, and the model
that enforces it.

This file exists because the package had ZERO coverage: no test file imported
cura.household at all, so a mutation to may_call() — the single function every
dial site consults — survived the entire 368-test suite. A module whose
docstring says "the one rule this module exists to enforce" had nothing
enforcing the enforcement.
"""
from __future__ import annotations

import pytest

from cura.household import (
    CheckIn, Household, Member, Purpose, Reach, may_call,
)


def _member(reach: Reach, **kw) -> Member:
    """A real Member with a genuinely dialable number, so that ONLY the
    recorded permission stands between this person and a phone call."""
    defaults = dict(member_id="june", name="June", phone="+1 307 555 0101")
    defaults.update(kw)
    return Member(reach=reach, **defaults)


class TestMayCallIsTheOnlyGate:
    """may_call(member, purpose) is THE permission check; nothing else may
    answer. These tests pin its whole truth table, not one row of it."""

    @pytest.mark.parametrize("purpose", list(Purpose))
    @pytest.mark.parametrize("reach", [Reach.NEVER, Reach.UNKNOWN])
    def test_never_and_unknown_are_never_dialled_for_any_purpose(
            self, reach, purpose):
        """MUTATION CLOSED: may_call's final arm — `return False  # NEVER and
        UNKNOWN are never dialled` — was flipped to `return True` and the
        whole suite stayed green, because no test imported this package.

        What the household would have experienced: the single permission
        function answered yes for the woman with late-stage dementia, whose
        reach is NEVER precisely because she cannot answer a phone. Cura
        would have placed scheduled check-ins AND emergency escalation calls
        to her — the exact failure all three reviewed designs had, and the
        one rule this module exists to enforce. UNKNOWN would have fared the
        same: "we never discussed it" silently became "yes".

        Parametrized over every member of Purpose, so the day a third purpose
        is added it is covered here without an edit: the property is "NEVER
        and UNKNOWN are never dialled for ANY purpose", not "for these two".
        """
        m = _member(reach)
        assert may_call(m, purpose) is False, (
            f"may_call answered yes for reach={reach.value!r}, "
            f"purpose={purpose.value!r} — Cura would dial a person who must "
            f"never be dialled (or whom nobody has said Cura may dial)")

    def test_the_full_permission_table(self):
        """Every (reach, purpose) pair, exhaustively, so no single arm of
        may_call can be flipped — permissive OR restrictive — without a test
        noticing. SCHEDULED answers yes to everything; ON_REQUEST answers yes
        only to HELP (a reason, never a schedule); NEVER and UNKNOWN answer
        no to everything.
        """
        table = {
            (Reach.SCHEDULED, Purpose.CHECKIN): True,
            (Reach.SCHEDULED, Purpose.HELP): True,
            (Reach.ON_REQUEST, Purpose.CHECKIN): False,
            (Reach.ON_REQUEST, Purpose.HELP): True,
            (Reach.NEVER, Purpose.CHECKIN): False,
            (Reach.NEVER, Purpose.HELP): False,
            (Reach.UNKNOWN, Purpose.CHECKIN): False,
            (Reach.UNKNOWN, Purpose.HELP): False,
        }
        # The table above must cover the whole domain — if an enum grows,
        # this test demands a decided answer rather than silently skipping.
        assert set(table) == {(r, p) for r in Reach for p in Purpose}, (
            "Reach or Purpose gained a member the permission table has no "
            "decided answer for")
        for (reach, purpose), allowed in table.items():
            assert may_call(_member(reach), purpose) is allowed, (
                f"may_call({reach.value!r}, {purpose.value!r}) should be "
                f"{allowed}")

    @pytest.mark.parametrize("reach", [Reach.NEVER, Reach.UNKNOWN])
    def test_a_schedule_cura_may_not_act_on_is_rejected_at_construction(
            self, reach):
        """Member.__post_init__ consults may_call, so under the same mutation
        (`return True` for NEVER/UNKNOWN) a Member marked never-to-call could
        be constructed WITH scheduled check-ins and no one would object.

        What the household would have experienced: a config that promises the
        woman with dementia an evening check-in call — a schedule Cura may
        not act on, a promise it cannot keep — accepted without a word.
        """
        with pytest.raises(ValueError):
            _member(reach, checkins=(CheckIn(slot="evening"),))


class TestTheFirstHouseholdIsNeverDialledWrong:
    """The first real household, end to end through the model: Ray (seventies,
    failing eyesight, sole caregiver, SCHEDULED) and June (late-stage
    dementia, cannot answer a phone, NEVER). Distinct numbers on purpose, so
    callable_for's shared-landline number exclusion cannot mask a permission
    failure — only may_call stands between June and a ringing phone."""

    def _household(self) -> Household:
        june = Member(member_id="june", name="June",
                      phone="+1 307 555 0101", reach=Reach.NEVER)
        ray = Member(member_id="ray", name="Ray",
                     phone="+1 307 555 0102", reach=Reach.SCHEDULED,
                     cares_for=("june",),
                     checkins=(CheckIn(slot="evening", about=("june", "ray")),))
        return Household(members={"june": june, "ray": ray})

    def test_no_dial_site_query_ever_returns_june(self):
        """MUTATION CLOSED (same mutation, at the dial sites): with may_call
        answering yes for NEVER, every dial-facing query in the model offers
        June up — callable_for lists her for check-ins and for help,
        responders_for names her as the person to call when Ray is the one
        lying on the floor, and profile_for hands her real number to voice.py
        and escalation.py, which dial profile.phone without ever having been
        taught about reach.

        What the household would have experienced: scheduled calls ringing
        beside a woman who cannot answer them, and — when Ray needs help —
        Cura's emergency path calling HER instead of a human who can come.
        """
        hh = self._household()
        for purpose in Purpose:
            offered = [m.member_id for m in hh.callable_for(purpose)]
            assert "june" not in offered, (
                f"callable_for({purpose.value!r}) offered june, who is "
                f"marked never-to-call")
        responders = [m.member_id for m in hh.responders_for("ray")]
        assert "june" not in responders, (
            "when Ray needs help, Cura's responder list names the woman "
            "with late-stage dementia")
        assert [m.member_id for m, _ in hh.scheduled_calls()] == ["ray"], (
            "the schedule of calls Cura should place is not exactly Ray's")
        assert hh.profile_for("june").phone == "", (
            "June's projection carries a dialable phone — every legacy dial "
            "site reads profile.phone, so she would be called by code that "
            "has never heard of reach")


class TestSharedLandlineExclusionIsFormatBlind:
    """callable_for's EXCLUSION BY PHONE NUMBER must compare normalized
    digits, never raw stored strings. These tests pin the property that the
    exclusion survives format drift — any mix of '(307) 555-0101',
    '307-555-0101', '3075550101' — not one blessed spelling of one number."""

    def _household(self, ray_phone: str, walt_phone: str) -> Household:
        """Ray and Walt share one rural landline (same digits, possibly
        different stored formats); Martha is a neighbour on her own line.
        All three are real Members with dialable numbers and permissive
        reach, so ONLY the number-exclusion logic decides who is offered."""
        ray = Member(member_id="ray", name="Ray",
                     phone=ray_phone, reach=Reach.SCHEDULED)
        walt = Member(member_id="walt", name="Walt",
                      phone=walt_phone, reach=Reach.ON_REQUEST)
        martha = Member(member_id="martha", name="Martha",
                        phone="+1 307 555 0199", reach=Reach.ON_REQUEST)
        return Household(members={"ray": ray, "walt": walt, "martha": martha})

    @pytest.mark.parametrize("ray_phone, walt_phone", [
        ("(307) 555-0101", "3075550101"),      # formatted vs bare digits
        ("3075550101", "(307) 555-0101"),      # bare digits vs formatted
        ("307-555-0101", "(307) 555 0101"),    # two different formattings
        ("(307) 555-0101", "(307) 555-0101"),  # identical raw strings
    ])
    def test_excluding_ray_also_excludes_everyone_on_his_landline(
            self, ray_phone, walt_phone):
        """MUTATION CLOSED: callable_for built skip_numbers from the RAW
        stored string — `self.members[i].phone or ""` with the
        `re.sub(r"\\D", "", ...)` normalization forgotten — while the
        membership check on the other side still compared normalized digits.
        A raw '(307) 555-0101' in the skip set can never equal a normalized
        '3075550101', so exclusion-by-number silently stopped working the
        moment two stored formats differed (and, because only one side was
        normalized, even when they matched).

        What the household would have experienced: Ray collapses and raises
        the alarm. Cura excludes Ray by member_id, then dials 'Walt' — the
        other name on the same rural landline — and rings the phone in the
        room where Ray is lying, believing it is calling someone else. The
        module's own docstring calls this out as the reviewed design's flaw;
        the normalization on BOTH sides of the comparison is the entire fix.

        The property, not the instance: parametrized over stored-format
        pairs that all denote the same line, including identical raw
        strings — every pair must exclude Walt, and none may swallow
        Martha, whose line really is different.
        """
        hh = self._household(ray_phone, walt_phone)
        offered = [m.member_id for m in
                   hh.callable_for(Purpose.HELP, excluding=("ray",))]
        assert "walt" not in offered, (
            f"with Ray stored as {ray_phone!r} and Walt as {walt_phone!r} "
            f"(the same landline), excluding Ray still offered Walt — Cura "
            f"would ring the phone in the room where Ray is lying")
        assert "martha" in offered, (
            "the exclusion swallowed Martha, whose number is genuinely "
            "different — Ray's emergency would find nobody at all")
        assert "ray" not in offered, "the excluded member himself was offered"

    def test_responders_for_never_offers_the_fallen_caregivers_own_line(self):
        """The same property through the emergency path callers actually use:
        responders_for(ray) must not name anyone whose 'different' number is
        Ray's own landline in another format, and must still find the
        neighbour who can come.
        """
        hh = self._household("(307) 555-0101", "3075550101")
        responders = [m.member_id for m in hh.responders_for("ray")]
        assert responders == ["martha"], (
            f"when Ray needs help the responder list is {responders!r}; "
            f"'walt' here is Ray's own landline wearing a different format")


from cura.household import dialable  # appended with the tests that guard it


class TestDialableRejectsNumbersNobodyCanRing:
    """dialable() — the household copy of "is this a number a phone network
    will actually connect". escalation._dialable is a second copy of the same
    rule and is guarded by its own tests; THIS copy had none, so the two can
    drift apart silently. These tests pin the property on the household side:
    fewer than ten digits is junk, ten-plus real digits (in any formatting)
    is a number.
    """

    @pytest.mark.parametrize("junk", [
        "555",            # the classic junk entry: a fragment, not a number
        "911",            # a short code is not a person Cura can summon
        "307555010",      # nine digits — one short of a number is not a number
        "3", "30", "307", "3075", "30755", "307555", "3075550", "30755501",
        "555-0101",       # seven digits wearing local-number formatting
        555,              # a non-string that stringifies to digit junk
        "+",              # the old norm_phone("") output the docstring warns of
        "", None,         # nothing at all
    ])
    def test_fewer_than_ten_digits_is_never_dialable(self, junk):
        """MUTATION CLOSED: cura/household/__init__.py:83 —
        `len(digits) >= 10` was mutated to `len(digits) > 0` and all 530
        tests stayed green, because nothing anywhere exercised this copy of
        the rule (the new dialable tests guard only the duplicate in
        cura/comms/escalation.py).

        What the household would have experienced: a junk entry like '555'
        counted as a reachable number, so blocking_problems() stayed silent
        for a household where nobody can actually be reached. Cura runs,
        promises Ray help, schedules calls against a three-digit fragment —
        and the night he needs someone, it can summon no one.

        The property, not the instance: every digit-count from one through
        nine, in several shapes, is rejected — not just the one string '555'.
        """
        assert dialable(junk) is False, (
            f"dialable({junk!r}) said yes to a number no phone network can "
            f"connect — Cura would count an unreachable person as reachable")

    @pytest.mark.parametrize("number", [
        "3075550101",          # exactly ten bare digits: the boundary itself
        "+1 307 555 0101",     # E.164-ish with country code and spaces
        "1-307-555-0101",      # eleven digits, dashed
        "(307) 555-0101",      # parenthesised local format
    ])
    def test_ten_real_digits_in_any_formatting_is_dialable(self, number):
        """The other half of the property, so the rule cannot drift stricter
        either: a genuine ten-digit number is dialable however it is
        formatted, and exactly ten digits (the boundary the mutation moved)
        answers yes. Without this half, `>= 10` could quietly become `>= 11`
        and every real household number would be refused instead.
        """
        assert dialable(number) is True, (
            f"dialable({number!r}) refused a genuine number — a reachable "
            f"household would be reported as unreachable")

    def test_a_junk_help_number_blocks_the_household_out_loud(self):
        """The same mutation, felt where it hurts: the readiness gate.

        MUTATION: with `len(digits) > 0`, Ray's phone recorded as '555'
        counts as dialable, so callable_for(HELP) finds a 'responder',
        blocking_problems() returns [] — Cura starts up, promises help it
        cannot summon — and scheduled_calls() emits check-in calls to a
        three-digit fragment that will never ring anywhere.

        Correct behaviour, pinned here: a household whose only help contact
        has a junk number does NOT run silently. blocking_problems() names
        both facts (nobody callable for help; check-ins scheduled against an
        undialable number), no calls are scheduled, and Ray is not counted
        reachable. June has a real number but reach=NEVER — so the ONLY
        thing standing between this household and false silence is dialable
        rejecting '555'.
        """
        june = Member(member_id="june", name="June",
                      phone="+1 307 555 0101", reach=Reach.NEVER)
        ray = Member(member_id="ray", name="Ray", phone="555",
                     reach=Reach.SCHEDULED, cares_for=("june",),
                     checkins=(CheckIn(slot="evening", about=("june", "ray")),))
        hh = Household(members={"june": june, "ray": ray})

        assert hh.callable_for(Purpose.HELP) == [], (
            "a three-digit fragment was offered as someone Cura can call "
            "for help")
        problems = hh.blocking_problems()
        assert problems, (
            "blocking_problems() stayed silent for a household where nobody "
            "can actually be reached — Cura would run and promise help it "
            "cannot summon")
        assert hh.scheduled_calls() == [], (
            "check-in calls were scheduled against a number that will never "
            "ring anywhere")
        assert ray.reachable is False, (
            "Ray was counted reachable on the strength of '555'")


class TestReadinessAsksTheHelpPermission:
    """blocking_problems' one genuine blocker is 'nobody can be reached when
    someone needs help' — a question about Purpose.HELP and nothing else.

    Because SCHEDULED grants both purposes, HELP-callable is always a
    superset of CHECKIN-callable; the ONLY household that can tell the two
    purposes apart at this gate is one whose every helper is ON_REQUEST.
    That household is not a corner case — it is the shape the module's own
    docstring says the first real household takes."""

    def _household(self, helper_reach: Reach) -> Household:
        """June (late-stage dementia, NEVER — she cannot answer a phone) and
        one helper on a real, dialable line whose recorded permission is the
        parameter. Nobody has check-ins, so the only thing blocking_problems
        can possibly say is whether anyone answers for help."""
        june = Member(member_id="june", name="June",
                      phone="+1 307 555 0101", reach=Reach.NEVER)
        walt = Member(member_id="walt", name="Walt",
                      phone="+1 307 555 0199", reach=helper_reach,
                      cares_for=("june",))
        return Household(members={"june": june, "walt": walt})

    @pytest.mark.parametrize("helper_reach, runnable", [
        (Reach.SCHEDULED, True),
        (Reach.ON_REQUEST, True),   # the only row that separates the purposes
        (Reach.NEVER, False),
        (Reach.UNKNOWN, False),
    ])
    def test_runnable_exactly_when_someone_answers_for_help(
            self, helper_reach, runnable):
        """MUTATION CLOSED: blocking_problems' gate was flipped from
        `if not self.callable_for(Purpose.HELP):` to
        `if not self.callable_for(Purpose.CHECKIN):` and the entire suite
        stayed green — zero tests exercised readiness. That is the
        purpose-drift trap the module documents: the moment check-in and
        help permissions are consulted in two places, one of them asks the
        wrong question and the drift is silent.

        What the household would have experienced: June's only helper is
        marked ON_REQUEST — call him when there is a reason, never on a
        schedule. He IS reachable for help, which is the only thing that
        genuinely blocks. The mutated gate asks the check-in question
        instead, finds nobody, and declares the household unrunnable:
        'there is nobody Cura can call for help' — over a man standing by
        his phone. The first real household becomes unconfigurable again,
        refused service over the exact fact this model exists to hold.

        The property, not the instance: every Reach a sole helper can carry,
        with the decided answer for each — runnable exactly when may_call
        (helper, HELP) holds. A restrictive flip (blocking the ON_REQUEST
        household) and a permissive flip (running with no helper at all)
        both land on a failing row.
        """
        problems = self._household(helper_reach).blocking_problems()
        if runnable:
            assert problems == [], (
                f"a household whose helper is {helper_reach.value!r} — "
                f"reachable for help — was declared unrunnable: {problems!r}")
        else:
            assert problems, (
                f"helper reach {helper_reach.value!r} means NOBODY answers "
                f"when someone needs help, yet blocking_problems saw no "
                f"reason not to run")
            assert any("help" in p for p in problems), (
                f"the household is unrunnable but no problem names the real "
                f"reason (nobody callable for help): {problems!r}")


class TestProjectionPhoneIsThePermissionMadeLegible:
    """profile_for's phone field is how the permission reaches legacy code:
    voice.py, escalation.py and checkin_composer.py dial profile.phone and
    have never heard of Reach. The rule has TWO halves — blank when Cura may
    not place a check-in call, the REAL number when it may — and both must be
    pinned, because a branch swap satisfies any test that looks at only one.
    """

    _NUMBER = "+1 307 555 0101"

    def _projected(self, reach: Reach) -> tuple[Member, str]:
        """One real Member with a genuinely dialable number in a real
        Household, through the real projection — so the ONLY thing deciding
        what lands in profile.phone is the recorded permission."""
        m = Member(member_id="pat", name="Pat",
                   phone=self._NUMBER, reach=reach)
        hh = Household(members={"pat": m})
        return m, hh.profile_for("pat").phone

    def test_the_full_projection_phone_table(self):
        """MUTATION CLOSED: cura/household/__init__.py:299 — the projection's
        branches were swapped, `phone=m.phone if may_call(m, Purpose.CHECKIN)
        else ""` becoming `phone="" if may_call(m, Purpose.CHECKIN) else
        m.phone` — handing the real number to exactly the people Cura may
        not call, and blanking it for exactly the people it must.

        What the household would have experienced, both halves at once: the
        NEVER-wife's real number lands in her profile.phone, so every legacy
        dial site — code never taught about reach — dials the woman with
        late-stage dementia who cannot answer a phone. Meanwhile the
        husband's own profile phone is blank, so his scheduled check-ins
        silently cannot be placed: no error, no call, nobody checking on the
        household that was promised checking.

        The property, not the instance: the whole Reach domain with a decided
        answer for each — the real number exactly when a check-in call is
        permitted, blank otherwise. One row alone cannot pin a swap (each
        branch is the other's else), and a table over only the blank rows
        would bless a mutation that blanks BOTH branches. If Reach grows a
        member, this test demands a decided answer rather than silently
        skipping it.
        """
        table = {
            Reach.SCHEDULED: self._NUMBER,  # the one reach check-ins may dial
            Reach.ON_REQUEST: "",           # help-only: no scheduled dialling
            Reach.NEVER: "",                # must never be dialled at all
            Reach.UNKNOWN: "",              # nobody has said; dial nothing
        }
        assert set(table) == set(Reach), (
            "Reach gained a member the projection-phone table has no "
            "decided answer for")
        for reach, expected in table.items():
            member, projected = self._projected(reach)
            assert projected == expected, (
                f"profile_for projected phone {projected!r} for "
                f"reach={reach.value!r}; expected {expected!r} — a wrong "
                f"number here is either a forbidden call placed or a "
                f"promised call silently dropped")
            assert member.phone == self._NUMBER, (
                "the projection erased the number from the Member itself — "
                "it is a fact about the person and must survive blanking")

    def test_the_first_household_projects_both_halves_at_once(self):
        """The same rule through the first real household, both people in one
        assertion pair — the shape a branch swap inverts exactly.

        Under the swap: Ray (SCHEDULED, evening check-ins) projects
        phone="" — so the calls the model itself schedules via
        scheduled_calls() cannot be placed by any dial site that reads his
        profile — while June (NEVER) projects her real number to code that
        dials whatever profile.phone holds. Correct behaviour, pinned here:
        Ray's projection carries the number his scheduled check-ins will be
        dialled on, June's carries nothing, and her real number remains on
        her Member as a fact for humans to see.
        """
        june = Member(member_id="june", name="June",
                      phone="+1 307 555 0101", reach=Reach.NEVER)
        ray = Member(member_id="ray", name="Ray",
                     phone="+1 307 555 0102", reach=Reach.SCHEDULED,
                     cares_for=("june",),
                     checkins=(CheckIn(slot="evening", about=("june", "ray")),))
        hh = Household(members={"june": june, "ray": ray})

        assert hh.profile_for("ray").phone == "+1 307 555 0102", (
            "Ray has scheduled check-ins Cura may act on, but his projection "
            "carries no number — every one of those calls silently cannot "
            "be placed")
        assert hh.profile_for("june").phone == "", (
            "June's projection hands her real number to dial sites that "
            "have never heard of reach")
        assert june.phone == "+1 307 555 0101", (
            "June's number is a fact about June; the projection blanks the "
            "profile, never the person")


class TestTheConstructionGuardPointsTheRightWay:
    """Member.__post_init__ refuses exactly one thing: scheduled check-ins
    for a person the recorded permission says Cura may not call on a
    schedule. BOTH halves of that sentence are the property. A test suite
    that only checks the rejection half cannot see an inverted guard, and a
    suite that only constructs valid members incidentally cannot see a
    crash-on-valid-input — the inversion breaks both at once, and only a
    test that pins the accept side AND the reject side lands on it."""

    @pytest.mark.parametrize("reach, accepted", [
        (Reach.SCHEDULED, True),    # the only reach that grants a schedule
        (Reach.ON_REQUEST, False),  # "for a reason, never on a schedule"
        (Reach.NEVER, False),
        (Reach.UNKNOWN, False),
    ])
    def test_checkins_accepted_exactly_when_reach_grants_a_schedule(
            self, reach, accepted):
        """MUTATION CLOSED: cura/household/__init__.py:111 — the guard
        `if self.checkins and not may_call(self, Purpose.CHECKIN):` was
        inverted to `if self.checkins and may_call(self, Purpose.CHECKIN):`.

        What the household would have experienced: a total outage dressed
        as safety. Ray — the one person Cura exists to call — raises
        ValueError the moment his evening check-in is configured, so the
        household's phone service goes down on its own config. Meanwhile
        the exact state the guard was written to refuse — check-in calls
        scheduled for June, who cannot answer a phone — loads without a
        word. Every valid household crashes; every invalid one is welcomed.

        The property, not the instance: every Reach, with the decided
        answer HARD-CODED per row rather than derived from may_call — a
        test that computes its expectation from the function under suspicion
        would be dragged along by a mutation there. Accepted rows must
        really carry their schedule (not merely fail to raise); rejected
        rows must raise a ValueError that names the check-ins.
        """
        checkins = (CheckIn(slot="morning"),
                    CheckIn(slot="evening", about=("june",)))
        if accepted:
            m = _member(reach, checkins=checkins)
            assert m.checkins == checkins, (
                f"a member Cura may call on a schedule "
                f"(reach={reach.value!r}) lost their check-ins at "
                f"construction")
        else:
            with pytest.raises(ValueError) as exc:
                _member(reach, checkins=checkins)
            assert "check-ins" in str(exc.value), (
                f"the refusal for reach={reach.value!r} does not say what "
                f"was refused; the caregiver reading the error cannot fix "
                f"the config")

    @pytest.mark.parametrize("reach", list(Reach))
    def test_a_member_without_checkins_loads_under_any_reach(self, reach):
        """The guard is about the SCHEDULE, not the person. June — reach
        NEVER, no check-ins — is the first household's central fact, and a
        guard that fires without a schedule to object to would make her
        unrepresentable. Every Reach must construct cleanly when there is
        nothing scheduled, so recording a person can never be the error.
        """
        m = _member(reach)
        assert m.checkins == (), "the no-checkins member grew a schedule"
        assert m.reach is reach

    def test_the_first_households_own_config_loads_and_schedules_ray(self):
        """The same guard felt end to end, through Household.from_dict — the
        path a real saved config takes at startup.

        MUTATION: under the inverted guard this exact dict — Ray SCHEDULED
        with an evening check-in, June NEVER with none — raises ValueError
        inside from_dict while Ray's Member is being built. The household
        does not degrade; it fails to exist. Cura never starts, and the
        error blames the one correctly-configured line in the file.

        Correct behaviour, pinned: the config loads, Ray keeps his evening
        call about both of them, the schedule of calls Cura should place is
        exactly Ray's, and nothing blocks the household from running.
        """
        hh = Household.from_dict({"household": {"members": [
            {"member_id": "june", "name": "June",
             "phone": "+1 307 555 0101", "reach": "never"},
            {"member_id": "ray", "name": "Ray",
             "phone": "+1 307 555 0102", "reach": "scheduled",
             "cares_for": ["june"],
             "checkins": [{"slot": "evening", "about": ["june", "ray"]}]},
        ]}})
        assert set(hh.members) == {"june", "ray"}
        assert hh.members["ray"].checkins == (
            CheckIn(slot="evening", about=("june", "ray")),), (
            "Ray's evening check-in did not survive the load")
        assert [(m.member_id, c.slot) for m, c in hh.scheduled_calls()] == [
            ("ray", "evening")], (
            "the calls Cura should place are not exactly Ray's evening call")
        assert hh.blocking_problems() == [], (
            "a valid first-household config was refused at the readiness "
            "gate")
