"""Escalation tests that can actually fail.

The suite had 157 passing tests and two mutants applied to the real escalation
code — blanking caregiver_phone, and misdirecting crisis_alert to dial the elder
instead of her contacts — passed all of them. `test_morning_checkin` asserted
`"Lisinopril" in t or "medication" in t`, which the constant line "Press 1 if
you've taken your medications" satisfies on its own.

Every test here was verified by mutation: the code it covers was deliberately
broken and the test was confirmed to notice. A test never observed failing is not
known to test anything.
"""
import asyncio
import logging

import pytest

from cura.comms.escalation import build_escalation, escalation_readiness
from cura.comms.responder import CuraResponder
from cura.pulse.eldercare_pulse import ElderProfile


def _profile(**over):
    base = dict(
        name="Margaret Chen", preferred_name="Mags", phone="+15551234567",
        medications=[], emergency_contacts=[{"name": "Thomas", "phone": "+15559876543"}],
        primary_caregiver={"name": "Thomas", "phone": "+15559876543"},
        address="", morning_time=8, evening_time=19,
    )
    base.update(over)
    return ElderProfile(**base)


class _FakeVoice:
    def __init__(self):
        self.calls = []

    async def crisis_alert(self, profile, crisis_type, details):
        self.calls.append({"profile": profile, "type": crisis_type, "details": details})
        return [("delivered", None)]


class TestReadiness:
    def test_no_contact_phone_blocks_escalation(self):
        """The GUI can write emergency_contacts: [] under a screen saying
        'Cura is ready.' That configuration must not be servable."""
        problems = escalation_readiness(_profile(emergency_contacts=[],
                                                 primary_caregiver={}))
        assert problems, "a profile with nobody to call reported itself ready"
        assert any("nobody can be reached" in p for p in problems)

    def test_contact_without_a_number_does_not_count(self):
        """A named contact with no phone is the plausible-looking config that
        produces silence at the worst moment."""
        problems = escalation_readiness(
            _profile(emergency_contacts=[{"name": "Thomas", "phone": ""}],
                     primary_caregiver={"name": "Thomas", "phone": ""}))
        assert problems

    def test_complete_profile_is_ready(self):
        assert escalation_readiness(_profile()) == []


class TestEscalationFires:
    def test_build_returns_none_when_help_cannot_be_summoned(self):
        """None is a refusal, not a degraded mode."""
        assert build_escalation(_FakeVoice(),
                                _profile(emergency_contacts=[],
                                         primary_caregiver={})) is None

    def test_callback_actually_calls_crisis_alert(self):
        voice = _FakeVoice()
        cb = build_escalation(voice, _profile())
        assert cb is not None
        cb("Elder said: I fell and I can't get up")
        assert len(voice.calls) == 1, "help was requested and nobody was contacted"
        assert "fell" in voice.calls[0]["details"]

    def test_crisis_alert_receives_the_profile_with_the_contacts(self):
        """Guards the mutant that dialled the elder instead of her contacts."""
        voice = _FakeVoice()
        build_escalation(voice, _profile())("help")
        sent_to = voice.calls[0]["profile"].emergency_contacts
        assert sent_to and sent_to[0]["phone"] == "+15559876543"


class TestResponderPromise:
    def test_unwired_responder_does_not_promise_help(self):
        """The defect that started this: Cura told someone who had fallen that
        help was on the way while on_help_requested was None."""
        r = CuraResponder()
        said = r.handle_speech("I fell in the pantry and I can't get up")["say"].lower()
        assert "help is on the way" not in said
        assert "911" in said or "nine one one" in said

    def test_wired_responder_promises_and_delivers(self):
        got = []
        r = CuraResponder(on_help_requested=lambda m: got.append(m))
        said = r.handle_speech("I fell and I can't get up")["say"].lower()
        assert "help is on the way" in said
        assert got, "Cura promised help and did not call the callback"

    def test_warm_wording_survives(self):
        """A first attempt at the safety fix flattened three responses into one
        and lost 'You're not alone' — the warmest thing Cura says."""
        r = CuraResponder(on_help_requested=lambda m: None)
        assert "not alone" in r.handle_dtmf("2", "checkin")["say"].lower()

    def test_unwired_responder_logs_an_error(self, caplog):
        """Silence about a failed escalation is how this stayed broken."""
        with caplog.at_level(logging.ERROR):
            CuraResponder().handle_dtmf("2", "checkin")
        assert any("NO CALLBACK" in r.message.upper() or
                   "no callback" in r.getMessage().lower() for r in caplog.records)


class TestDialability:
    """Guards the mutant `_dialable: len(digits) >= 10` -> `len(digits) >= 1`.

    That mutation degrades the dialability guard back to 'has any digit' --
    almost the original emptiness-only bug this function exists to prevent. A
    hand-edited config with a partial number like '555' would pass readiness,
    Cura would serve, and when he said 'I fell' the escalation would dial an
    undialable number and reach nobody while telling him help was coming.

    The property under test: any phone number with fewer than ten digits is
    undialable, wherever it appears in the profile -- not just the empty and
    bad-area-code instances the earlier tests happened to pin.
    """

    @pytest.mark.parametrize("partial", [
        "555",            # bare exchange, the classic hand-edit
        "911",            # 'they wrote 911 in the contact field'
        "5551234",        # seven-digit local number, no area code
        "555-1234",       # same, formatted
        "+1 555 987",     # trunk prefix plus a fragment
        "555123456",      # nine digits: one short of dialable, the boundary
    ])
    def test_partial_contact_number_blocks_readiness(self, partial):
        """A short-but-nonempty contact number must not count as reachable."""
        problems = escalation_readiness(_profile(
            emergency_contacts=[{"name": "Thomas", "phone": partial}],
            primary_caregiver={"name": "Thomas", "phone": partial}))
        assert any("nobody can be reached" in p for p in problems), (
            f"contact number {partial!r} was treated as dialable -- Cura would "
            f"serve, promise help, and reach nobody")

    @pytest.mark.parametrize("partial", ["555", "5551234", "555123456"])
    def test_partial_elder_number_blocks_readiness(self, partial):
        """The elder's own line goes through the same guard: a partial number
        there means Cura cannot place the check-in call it exists to make."""
        problems = escalation_readiness(_profile(phone=partial))
        assert any("no phone number Cura can dial" in p for p in problems), (
            f"elder number {partial!r} was treated as dialable")

    def test_ten_digits_is_the_boundary(self):
        """Nine digits undialable, ten dialable -- so this class cannot rot
        into 'reject everything' and pass vacuously."""
        assert escalation_readiness(_profile(
            phone="5551234567",
            emergency_contacts=[{"name": "Thomas", "phone": "5559876543"}],
            primary_caregiver={"name": "Thomas", "phone": "5559876543"})) == []

    def test_partial_number_config_refuses_to_serve(self):
        """The household consequence, end to end: build_escalation must return
        None (a refusal, not a degraded mode) for a partial-number config."""
        assert build_escalation(_FakeVoice(), _profile(
            emergency_contacts=[{"name": "Thomas", "phone": "555"}],
            primary_caregiver={"name": "Thomas", "phone": "555"})) is None


class TestTenDigitBoundary:
    """Guards the mutant `_dialable: len(digits) >= 10` -> `len(digits) > 10`.

    That mutation declares a valid 10-digit US number undialable. A household
    that types '3075550134' into the JSON by hand -- no +1, no punctuation,
    the way everyone writes their own phone number -- fails readiness,
    build_escalation returns None, and Cura refuses to serve a perfectly
    workable config. It fails safe and visible, but the rural household is
    locked out of the service over a country code they had no reason to type.

    Nothing caught it because every dialable number anywhere in the suite was
    11 digits (+1 E.164); the 10-digit lower edge of dialability was never
    exercised. The property: ten digits IS dialable -- in every position the
    guard consults, however the number is punctuated.
    """

    @pytest.mark.parametrize("ten_digit", [
        "3075550134",        # bare, exactly as a hand-edited config gets it
        "(307) 555-0134",    # copied off paper
        "307-555-0134",
        "307.555.0134",
    ])
    def test_ten_digit_us_number_is_dialable_everywhere(self, ten_digit):
        """A profile whose every number is a 10-digit US number must pass
        readiness, and build_escalation must hand back a working callback."""
        profile = _profile(
            phone=ten_digit,
            emergency_contacts=[{"name": "Thomas", "phone": ten_digit}],
            primary_caregiver={"name": "Thomas", "phone": ten_digit})
        assert escalation_readiness(profile) == [], (
            f"{ten_digit!r} is a dialable US number; declaring it undialable "
            f"locks a workable household out of the service")
        voice = _FakeVoice()
        cb = build_escalation(voice, profile)
        assert cb is not None, (
            f"build_escalation refused to serve over {ten_digit!r} -- a valid "
            f"number missing only the country code")
        cb("smoke detector going off and no answer at the door")
        assert len(voice.calls) == 1, (
            "the callback was built but did not summon help")


class TestElderPhoneCheck:
    """Guards the mutant that deletes the elder-phone check from
    escalation_readiness (`if not _dialable(profile.phone): problems.append(...)`).

    Under that mutation, a profile with flawless emergency contacts and no
    dialable number for the elder himself reports itself ready. Cura starts,
    and every scheduled check-in call silently fails to connect: a man with
    failing eyesight believes his wife is being checked on when nobody's
    phone ever rings. The reachable contacts are exactly what made the gap
    invisible -- every readiness test in the suite supplied a valid elder
    phone, so the elder-phone branch was never the branch that decided.

    The property: an undialable elder phone is a readiness problem in its own
    right, reported even when every contact is reachable, and it must make
    build_escalation refuse to serve -- whatever undialable shape the config
    hands us, not just the one empty-string instance.
    """

    @pytest.mark.parametrize("no_phone", [
        "",       # profile field never filled in
        None,     # JSON null from a hand-edited config
        "   ",    # whitespace that survives a form submit
        "+",      # what norm_phone("") used to return -- the historic trap
    ])
    def test_undialable_elder_phone_blocks_readiness_despite_good_contacts(
            self, no_phone):
        """The contacts being fine must not mask the elder's missing line."""
        problems = escalation_readiness(_profile(phone=no_phone))
        assert any("no phone number Cura can dial" in p for p in problems), (
            f"elder phone {no_phone!r} with reachable contacts reported "
            f"ready -- every check-in call would silently fail to connect")
        # And it is the elder-phone problem, not a conflation with the
        # contacts problem: the contacts in this profile ARE reachable.
        assert not any("nobody can be reached" in p for p in problems)

    def test_undialable_elder_phone_refuses_to_serve(self):
        """The household consequence, end to end: build_escalation must
        return None (a refusal, not a degraded mode) when the person Cura
        exists to call has no number Cura can dial."""
        assert build_escalation(_FakeVoice(), _profile(phone="")) is None


class TestEitherContactLegSuffices:
    """Guards the mutant `escalation_readiness:
    `if not contacts and not _dialable(caregiver...)` ->
    `if not contacts or not _dialable(caregiver...)`.

    The check exists to answer one question: can ANYBODY be summoned? A
    dialable emergency contact answers yes. A dialable primary caregiver
    answers yes. Under the mutation, a household that filled in emergency
    contacts but left primary_caregiver empty (or vice versa -- entered the
    caregiver during setup and never got to the contacts screen) is refused
    service at startup with a message claiming nobody can be reached, when
    help was in fact summonable. It fails safe, but it locks a legitimate
    config out of the service over a field that was never required.

    Nothing caught it because every ready-profile test filled BOTH legs,
    always with the same person and number, so `and` and `or` were
    indistinguishable. The property: EITHER leg alone is sufficient for
    readiness, and build_escalation must hand back a callback that actually
    summons help.
    """

    @pytest.mark.parametrize("no_caregiver", [
        {},                                  # setup screen never reached
        None,                                # JSON null from a hand-edit
        {"name": "Thomas", "phone": ""},     # named but numberless
    ])
    def test_contacts_alone_are_sufficient(self, no_caregiver):
        """Emergency contacts filled, no caregiver entry: ready, and serves."""
        profile = _profile(
            emergency_contacts=[{"name": "Thomas", "phone": "+15559876543"}],
            primary_caregiver=no_caregiver)
        assert escalation_readiness(profile) == [], (
            f"contacts are dialable but caregiver={no_caregiver!r} blocked "
            f"readiness -- a summonable household was refused service")
        voice = _FakeVoice()
        cb = build_escalation(voice, profile)
        assert cb is not None, (
            "build_escalation refused a profile whose emergency contacts "
            "could be reached")
        cb("Elder said: I smell gas")
        assert len(voice.calls) == 1, (
            "the callback was built but did not summon help")

    @pytest.mark.parametrize("no_contacts", [
        [],                                  # contacts screen never reached
        None,                                # JSON null from a hand-edit
        [{"name": "Thomas", "phone": ""}],   # named but numberless
    ])
    def test_caregiver_alone_is_sufficient(self, no_contacts):
        """Caregiver filled, no emergency contacts: ready, and serves."""
        profile = _profile(
            emergency_contacts=no_contacts,
            primary_caregiver={"name": "Thomas", "phone": "+15559876543"})
        assert escalation_readiness(profile) == [], (
            f"caregiver is dialable but contacts={no_contacts!r} blocked "
            f"readiness -- a summonable household was refused service")
        voice = _FakeVoice()
        cb = build_escalation(voice, profile)
        assert cb is not None, (
            "build_escalation refused a profile whose primary caregiver "
            "could be reached")
        cb("Elder said: I fell and I can't get up")
        assert len(voice.calls) == 1, (
            "the callback was built but did not summon help")

    def test_both_legs_empty_still_blocks(self):
        """The class must not rot into 'one leg is enough' by accepting zero
        legs: with neither a contact nor a caregiver, readiness must fail.
        (Keeps this class honest against the opposite drift.)"""
        problems = escalation_readiness(_profile(
            emergency_contacts=[], primary_caregiver={}))
        assert any("nobody can be reached" in p for p in problems)


class TestCaregiverFieldName:
    """Guards the mutant `escalation_readiness:
    `getattr(profile, "primary_caregiver", None)` ->
    `getattr(profile, "caregiver", None)` (wrong field name).

    ElderProfile has no attribute called `caregiver`, so under the mutation
    the getattr default silently absorbs the typo -- the same defect class as
    the _report_call bug, where reading fields an object does not have was
    invisible because nothing ever raised. The caregiver leg of readiness
    becomes permanently empty: `caregiver` is always {} and never dialable.

    The household consequence: a sole-caregiver household that filled in only
    primary_caregiver and no separate emergency contacts -- exactly the first
    household's shape, a man in his seventies who IS the emergency contact for
    his wife -- fails readiness at startup and is refused service, with a
    message claiming nobody can be reached when he is right there with a
    working phone.

    Why nothing caught it originally: no test had a dialable caregiver paired
    with empty/undialable emergency contacts, so the caregiver leg was never
    load-bearing on its own. The property: readiness must read the caregiver
    from the field the profile actually has, `primary_caregiver`, and that
    field alone -- with no other reachable number anywhere -- is sufficient
    to serve, and the help it summons must go to a profile carrying that
    caregiver.
    """

    def _sole_caregiver_profile(self):
        """The first household's shape: the caregiver is the only human with
        a reachable phone. No emergency contacts at all."""
        return ElderProfile(
            name="Eleanor", preferred_name="Ellie", phone="+13075550187",
            medications=[], emergency_contacts=[],
            primary_caregiver={"name": "Walt", "phone": "+13075550134"},
            address="", morning_time=8, evening_time=19,
        )

    def test_primary_caregiver_field_is_the_one_consulted(self):
        """A dialable primary_caregiver with zero emergency contacts must
        pass readiness. If readiness reads any other attribute name, the
        getattr default turns this household into 'nobody can be reached'."""
        problems = escalation_readiness(self._sole_caregiver_profile())
        assert problems == [], (
            f"sole-caregiver profile reported {problems!r} -- readiness is "
            f"not reading the primary_caregiver field the profile actually "
            f"has, and the only household shape we are built for is refused "
            f"service")

    def test_sole_caregiver_household_is_served_and_help_reaches_him(self):
        """End to end: build_escalation must hand back a callback, and firing
        it must summon help for the profile whose primary_caregiver is the
        one reachable person -- not refuse at startup, not fire into a void."""
        voice = _FakeVoice()
        profile = self._sole_caregiver_profile()
        cb = build_escalation(voice, profile)
        assert cb is not None, (
            "build_escalation refused the sole-caregiver household -- the "
            "caregiver fallback has silently vanished")
        cb("Elder said: Walt fell carrying wood and isn't answering me")
        assert len(voice.calls) == 1, (
            "the callback was built but did not summon help")
        sent = voice.calls[0]["profile"]
        assert sent.primary_caregiver.get("phone") == "+13075550134", (
            "crisis_alert was handed a profile without the caregiver's "
            "number -- the one person who could be reached is not in it")


class TestContactsFieldName:
    """Guards the mutant `escalation_readiness:
    `getattr(profile, "emergency_contacts", None)` ->
    `getattr(profile, "contacts", None)` (wrong field name).

    ElderProfile has no attribute called `contacts`, so under the mutation the
    getattr default silently absorbs the typo — the _report_call defect class
    again: reading a field the object does not have raises nothing and returns
    the default forever. The emergency-contacts leg of readiness becomes
    permanently empty, and readiness stands or falls on the caregiver entry
    alone.

    The household consequence: a config with three valid emergency contacts
    and a blank caregiver entry — a family that filled in the contacts screen
    and never the caregiver one — is refused service at startup as 'nobody can
    be reached' when three people were reachable. It fails safe, but a
    summonable household is locked out over a field it never needed.

    Why nothing caught it originally: contacts and caregiver were both-valid
    or both-invalid in every test, so losing one field entirely changed no
    test's outcome. TestEitherContactLegSuffices now trips over this mutant
    too, but only incidentally — its stated property is the and/or boolean,
    and a refactor faithful to that docstring could reopen this hole. This
    class pins the field-name property itself: readiness must read the
    contacts from the attribute ElderProfile actually has,
    `emergency_contacts`, and that list alone — no caregiver, no other
    reachable number — is sufficient to serve.
    """

    def _contacts_only_profile(self):
        """Three reachable people on the contacts screen, caregiver blank."""
        return ElderProfile(
            name="Eleanor", preferred_name="Ellie", phone="+13075550187",
            medications=[],
            emergency_contacts=[
                {"name": "Walt", "phone": "+13075550134"},
                {"name": "Dana", "phone": "+13075550158"},
                {"name": "Ruth", "phone": "+13075550171"},
            ],
            primary_caregiver={},
            address="", morning_time=8, evening_time=19,
        )

    def test_emergency_contacts_field_is_the_one_consulted(self):
        """Three dialable emergency contacts with a blank caregiver must pass
        readiness. If readiness reads any other attribute name, the getattr
        default makes this household 'nobody can be reached' — with three
        people reachable."""
        problems = escalation_readiness(self._contacts_only_profile())
        assert problems == [], (
            f"contacts-only profile reported {problems!r} — readiness is not "
            f"reading the emergency_contacts field the profile actually has, "
            f"and three reachable people have become invisible")

    def test_contacts_only_household_is_served_and_help_reaches_them(self):
        """End to end: build_escalation must hand back a callback, and firing
        it must summon help for the profile whose emergency_contacts are the
        reachable people — not refuse at startup, not fire into a void."""
        voice = _FakeVoice()
        profile = self._contacts_only_profile()
        cb = build_escalation(voice, profile)
        assert cb is not None, (
            "build_escalation refused the contacts-only household — the "
            "emergency_contacts leg of readiness has silently vanished")
        cb("Elder said: I fell in the kitchen and I can't get up")
        assert len(voice.calls) == 1, (
            "the callback was built but did not summon help")
        sent = voice.calls[0]["profile"].emergency_contacts
        assert [c["phone"] for c in sent] == [
            "+13075550134", "+13075550158", "+13075550171"], (
            "crisis_alert was handed a profile without the three reachable "
            "contacts — the people who could be summoned are not in it")
