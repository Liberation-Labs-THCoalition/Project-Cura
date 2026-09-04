"""Tests for voice interface — Cura's Twilio integration."""
from __future__ import annotations

import pytest
from cura.comms.voice import CuraVoice, CallResult, SMSResult
from cura.pulse.eldercare_pulse import ElderProfile


def _make_profile() -> ElderProfile:
    return ElderProfile(
        name="Margaret Chen",
        preferred_name="Margaret",
        phone="+15551234567",
        medications=[
            {"name": "Lisinopril", "time": "morning"},
            {"name": "Metformin", "time": "morning"},
            {"name": "Amlodipine", "time": "evening PM"},
        ],
        emergency_contacts=[
            {"name": "Sarah Chen", "phone": "+15559876543", "relation": "daughter"},
            {"name": "Tom Chen", "phone": "+15559876544", "relation": "son"},
        ],
        primary_caregiver={"name": "Sarah Chen", "phone": "+15559876543"},
        address="123 Elm Street, Springfield, IL",
    )


class TestTwiMLGeneration:
    def test_basic_twiml(self):
        voice = CuraVoice(dry_run=True)
        twiml = voice._build_twiml(["Hello Margaret"])
        assert "<Say" in twiml
        assert "Hello Margaret" in twiml
        assert "<Pause" in twiml

    def test_gather_twiml(self):
        voice = CuraVoice(dry_run=True, public_url="https://cura.example.org")
        twiml = voice._build_twiml(
            ["Press 1"], gather=True,
            gather_action=voice._gather_url("/voice/checkin-response"))
        assert "<Gather" in twiml
        assert "timeout" in twiml
        assert "didn't hear" in twiml

    def test_gather_has_an_action_url(self):
        """A Gather without an action posts back to the URL that served the
        TwiML — and these calls are created with inline twiml=, which has no
        URL. The keypress went nowhere. Pressing 2 for help reached nobody."""
        voice = CuraVoice(dry_run=True, public_url="https://cura.example.org")
        twiml = voice._build_twiml(
            ["Press 1"], gather=True,
            gather_action=voice._gather_url("/voice/checkin-response"))
        assert 'action="https://cura.example.org/voice/checkin-response"' in twiml

    def test_no_gather_offered_when_the_answer_cannot_reach_us(self):
        """Better to not offer the button than to offer one that does nothing.
        Someone pressing 2 for help and hearing nothing back is the failure
        this whole path exists to prevent."""
        voice = CuraVoice(dry_run=True, public_url="")
        twiml = voice._build_twiml(["Press 1"], gather=True, gather_action="")
        assert "<Gather" not in twiml

    def test_relative_action_without_public_url_is_refused(self):
        """A relative path is unreachable to Twilio, which dials in from the
        public internet — and the failure is invisible from our side: the call
        completes and no response ever arrives."""
        voice = CuraVoice(dry_run=True, public_url="")
        assert voice._gather_url("/voice/checkin-response") == ""


@pytest.mark.asyncio
class TestDryRunCalls:
    async def test_basic_call(self):
        voice = CuraVoice(dry_run=True)
        result = await voice.call("+15551234567", ["Hello"])
        assert result.answered
        assert result.call_sid == "dry_run"

    async def test_send_sms(self):
        voice = CuraVoice(dry_run=True)
        result = await voice.send_sms("+15551234567", "Test message")
        assert result.delivered
        assert result.message_sid == "dry_run"

    async def test_morning_checkin(self):
        voice = CuraVoice(dry_run=True)
        profile = _make_profile()
        result = await voice.morning_checkin(profile)
        assert result.answered
        assert "Lisinopril" in result.transcript or "medication" in result.transcript

    async def test_evening_checkin(self):
        voice = CuraVoice(dry_run=True)
        profile = _make_profile()
        result = await voice.evening_checkin(profile)
        assert result.answered

    async def test_alert_caregiver(self):
        voice = CuraVoice(dry_run=True)
        profile = _make_profile()
        call_result, sms_result = await voice.alert_caregiver(
            profile, "missed_checkin", "Margaret didn't answer morning check-in"
        )
        assert call_result.answered
        assert sms_result.delivered

    async def test_crisis_alert_contacts_all(self):
        voice = CuraVoice(dry_run=True)
        profile = _make_profile()
        results = await voice.crisis_alert(profile, "fall", "Fall detected at 2am")
        assert len(results) == 2

    async def test_call_log(self):
        voice = CuraVoice(dry_run=True)
        await voice.call("+15551234567", ["Test"])
        await voice.call("+15559876543", ["Test 2"])
        assert len(voice.call_log) == 2

    async def test_sms_log(self):
        voice = CuraVoice(dry_run=True)
        await voice.send_sms("+15551234567", "Test")
        assert len(voice.sms_log) == 1


class TestTwiMLEscaping:
    """Names and medications reach TwiML straight from the household's config.

    An ampersand or an angle bracket in either produces malformed XML that
    Twilio rejects, so the failure is not a mispronunciation -- it is a call
    that never happens. "Tylenol & Lisinopril" and a caregiver named
    "Tom & Barbara" were both enough to cancel every reminder silently.
    """

    HOSTILE = [
        "Tom & Barbara are coming by.",
        "Take 1 tablet if pain < 5 or > 7.",
        "Time for your Tylenol & Lisinopril.",
        'She said "I already took it".',
        "Hello</Say><Hangup/><Say>",
        """O'Brien & Sons <"test"> & more""",
    ]

    def _voice(self):
        from cura.comms.voice import CuraVoice
        return CuraVoice(account_sid="x", auth_token="y",
                         from_number="+15551112222",
                         public_url="https://example.org")

    @pytest.mark.parametrize("text", HOSTILE)
    def test_voice_twiml_stays_well_formed(self, text):
        import xml.etree.ElementTree as ET
        ET.fromstring(self._voice()._build_twiml([text]))

    @pytest.mark.parametrize("text", HOSTILE)
    def test_webhook_twiml_stays_well_formed(self, text):
        import xml.etree.ElementTree as ET
        from cura.comms import webhook as wh
        ET.fromstring(wh._twiml(wh._say(text)))

    @pytest.mark.parametrize("text", HOSTILE)
    def test_spoken_text_survives_verbatim(self, text):
        """Escaping must not change what she hears."""
        import xml.etree.ElementTree as ET
        root = ET.fromstring(self._voice()._build_twiml([text]))
        assert root.find("Say").text == text

    def test_markup_in_text_is_spoken_not_executed(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(
            self._voice()._build_twiml(["Hello</Say><Hangup/><Say>"]))
        assert root.find("Hangup") is None, "markup in a name became TwiML"
        assert root.find(".//Hangup") is None

    def test_attribute_injection_is_contained(self):
        """A poisoned public URL must not close the attribute and add verbs."""
        import xml.etree.ElementTree as ET
        v = self._voice()
        v._public_url = 'https://x.org/"><Hangup/><Gather action="'
        root = ET.fromstring(
            v._build_twiml(["hi"], gather=True,
                           gather_action=v._gather_url("/voice/r")))
        assert root.find(".//Hangup") is None


class TestPublicUrlResolvesFresh:
    """`cura run` is long-lived and built CuraVoice once, so a tunnel address
    that rotates left Cura holding a dead URL — and the symptom is silent: the
    call still places, the Gather just posts into nothing.

    Rather than depend on a stability guarantee from the other side of an
    integration we cannot verify, resolve it fresh each time.
    """

    def _voice(self, cfg=None, ctor=""):
        from cura.comms.voice import CuraVoice
        return CuraVoice(account_sid="x", auth_token="y", from_number="+1555",
                         public_url=ctor, config_path=str(cfg) if cfg else "")

    def _cfg(self, tmp_path, url):
        import json
        p = tmp_path / "m.json"
        p.write_text(json.dumps({"name": "M", "public_url": url}))
        return p

    def test_a_rotated_url_is_picked_up_without_a_restart(self, tmp_path):
        cfg = self._cfg(tmp_path, "https://first.example.org")
        v = self._voice(cfg)
        assert v._gather_url("/x") == "https://first.example.org/x"
        self._cfg(tmp_path, "https://rotated.example.org")
        assert v._gather_url("/x") == "https://rotated.example.org/x"

    def test_environment_takes_precedence(self, tmp_path, monkeypatch):
        cfg = self._cfg(tmp_path, "https://cfg.example.org")
        monkeypatch.setenv("CURA_PUBLIC_URL", "https://env.example.org")
        assert self._voice(cfg)._gather_url("/x") == "https://env.example.org/x"

    def test_a_missing_config_is_not_fatal(self, tmp_path):
        v = self._voice(tmp_path / "gone.json", ctor="https://ctor.example.org")
        assert v._gather_url("/x") == "https://ctor.example.org/x"

    def test_a_half_written_config_is_not_fatal(self, tmp_path):
        p = tmp_path / "m.json"
        p.write_text('{"name": "M", "public_ur')      # truncated mid-write
        v = self._voice(p, ctor="https://ctor.example.org")
        assert v._gather_url("/x") == "https://ctor.example.org/x"

    def test_with_no_url_anywhere_it_still_refuses_rather_than_guessing(self):
        v = self._voice()
        assert v._gather_url("/x") == ""
        assert "<Gather" not in v._build_twiml(["hi"], gather=True,
                                               gather_action=v._gather_url("/x"))


class TestCheckInReportingTellsTheTruth:
    """Built from a REAL CallResult, not a stub with imagined fields.

    The first version of _report_call read `success` and `sid`; CallResult has
    `answered` and `call_sid`. Every successful check-in therefore reported
    FAILED — a log that always said "sent" replaced by one that always said
    "failed". A stub carrying the fields I assumed would have passed both.
    """

    def _report(self, result):
        import io, contextlib
        from cura.__main__ import _report_call
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _report_call("Morning", "Margaret", result)
        return buf.getvalue()

    def _result(self, **kw):
        from datetime import datetime, timezone
        from cura.comms.voice import CallResult
        base = dict(timestamp=datetime.now(timezone.utc),
                    to_number="+13075550134", answered=False)
        base.update(kw)
        return CallResult(**base)

    def test_an_answered_call_is_reported_as_placed(self):
        out = self._report(self._result(answered=True, call_sid="CA123"))
        assert "FAILED" not in out
        assert "placed" in out

    def test_an_unanswered_call_is_reported_as_failed(self):
        out = self._report(self._result(answered=False, error="busy"))
        assert "FAILED" in out and "busy" in out

    def test_no_result_at_all_is_reported_as_failed(self):
        assert "FAILED" in self._report(None)

    def test_every_field_it_reads_exists_on_CallResult(self):
        """Pins the actual contract, so a rename cannot silently invert this."""
        from cura.comms.voice import CallResult
        import dataclasses
        fields = {f.name for f in dataclasses.fields(CallResult)}
        for name in ("answered", "error"):
            assert name in fields, f"_report_call reads {name!r}, CallResult has no such field"


class TestWebhookSignatureGate:
    """The webhook accepts exactly the requests Twilio signed — no others.

    Mutation this closes: webhook.py's before_request verification
        if not validator.validate(url, form, signature):   # correct
        if validator.validate(url, form, signature):       # mutant
    survived the entire suite, because no test ever built the Flask app or
    sent a request through _install_twilio_signature_check — the only related
    test was an AST check that the call site passes auth_token. Inverted, the
    gate rejects every legitimate Twilio POST with 403, so Margaret presses 1
    and her answer never reaches Cura — while accepting every forged or
    unsigned request, so a scanner that found the URL could confirm her
    medications were taken and Cura would stop following up. That is the
    exact attack the function's own docstring says an audit demonstrated.

    These tests send real signed and unsigned requests through the real Flask
    app, signing with the same twilio RequestValidator the gate verifies
    with, and land on a real CuraResponder — so the property under test is
    the gate itself, not one blessed request string.
    """

    TOKEN = "test-auth-token-abc123"

    def _client(self):
        from cura.comms.responder import CuraResponder
        from cura.comms import webhook as wh
        confirmed = []
        responder = CuraResponder(
            on_medication_confirmed=lambda: confirmed.append(True))
        app = wh.create_app(responder=responder, elder_name="Margaret",
                            auth_token=self.TOKEN)
        return app.test_client(), confirmed

    def _sign(self, url, params):
        """Sign the way Twilio does — with twilio's own validator."""
        from twilio.request_validator import RequestValidator
        return RequestValidator(self.TOKEN).compute_signature(url, params)

    def test_a_correctly_signed_twilio_post_is_accepted(self):
        """Her keypress must reach Cura. Under the inverted gate this very
        request — signed exactly as Twilio signs it — came back 403 and her
        confirmation of her own medications reached nobody."""
        client, confirmed = self._client()
        form = {"Digits": "1"}
        sig = self._sign("http://localhost/voice/checkin-response", form)
        resp = client.post("/voice/checkin-response", data=form,
                           headers={"X-Twilio-Signature": sig})
        assert resp.status_code == 200
        assert confirmed, "a genuine keypress of 1 never fired on_medication_confirmed"

    def test_an_unsigned_post_is_rejected_before_the_responder(self):
        """The audit's attack verbatim: an unsigned POST of Digits=1. It must
        get 403 and must NOT fire on_medication_confirmed — a forged
        confirmation is the one injection that looks exactly like success."""
        client, confirmed = self._client()
        resp = client.post("/voice/checkin-response", data={"Digits": "1"})
        assert resp.status_code == 403
        assert not confirmed, "a forged confirmation fired on_medication_confirmed"

    def test_a_garbage_signature_is_rejected(self):
        client, confirmed = self._client()
        resp = client.post("/voice/checkin-response", data={"Digits": "1"},
                           headers={"X-Twilio-Signature": "bm90IHR3aWxpbw=="})
        assert resp.status_code == 403
        assert not confirmed

    def test_a_signature_over_a_different_body_is_rejected(self):
        """The signature covers the exact POST body. A captured signature for
        one body replayed with Digits swapped in is the tamper the validator
        exists to stop; accepting it lets an attacker turn any recorded
        request into a medication confirmation."""
        client, confirmed = self._client()
        sig = self._sign("http://localhost/voice/checkin-response",
                         {"Digits": "2"})
        resp = client.post("/voice/checkin-response", data={"Digits": "1"},
                           headers={"X-Twilio-Signature": sig})
        assert resp.status_code == 403
        assert not confirmed

    def test_health_is_the_only_unsigned_door(self):
        """GET /health stays open for liveness probes — and only that: the
        same path must not open POST routes."""
        client, _ = self._client()
        assert client.get("/health").status_code == 200

    @pytest.mark.parametrize("missing_token", ["", None])
    def test_a_missing_auth_token_refuses_to_build_the_app_at_all(
            self, missing_token):
        """create_app with no auth token must raise, not serve.

        Mutation this closes: webhook.py's _install_twilio_signature_check
            if not auth_token: raise RuntimeError(...)   # correct
            if not auth_token: return                    # mutant
        survived the suite because the only related test was an AST check
        that the production call site passes the auth_token kwarg — nothing
        ever called create_app with an empty token and asserted it refuses.

        Under the mutant the guard returns before installing the
        before_request check, so create_app quietly hands back a Flask app
        with NO signature verification on any route. That is the exact
        failure the function's own docstring calls worse than no auth layer:
        it reports as present while anyone who found the URL could POST
        Digits=1 and confirm the resident's medications on her behalf —
        and Cura, believing her, would stop following up. A startup crash
        the operator sees beats an open door nobody sees.

        The property: for every falsy token, no app object is ever handed
        back — misconfiguration is refused at build time, not discovered
        at exploit time. Not pinned to one token spelling; empty string and
        None both take the same guard.
        """
        from cura.comms.responder import CuraResponder
        from cura.comms import webhook as wh
        confirmed = []
        responder = CuraResponder(
            on_medication_confirmed=lambda: confirmed.append(True))
        with pytest.raises(RuntimeError):
            wh.create_app(responder=responder, elder_name="Margaret",
                          auth_token=missing_token)
        assert not confirmed, (
            "building a refused app must not fire medication callbacks")


class TestVoiceRoutesReadTwilioFormKeys:
    """The voice routes read the keypress under the exact key Twilio posts.

    Mutation this closes: webhook.py checkin_response (line 145)
        digits = request.form.get("Digits", "")   # correct — Twilio's spelling
        digits = request.form.get("digits", "")   # mutant — never matches

    Twilio posts the keypress capitalised: Digits. Form keys are
    case-sensitive, so under the mutant every keypress during a check-in
    call is invisible — the route falls through to the empty-response
    branch. She presses 1 after taking her medications: "I didn't catch
    that. Goodbye for now.", and no confirmation is recorded, so Cura keeps
    believing the medication was missed. She presses 2 because she needs
    help: the same goodbye, and nobody is ever called. A help request that
    reaches nobody, from a phone in rural Wyoming, is the exact failure this
    system exists to prevent.

    It survived because the responder tests call handle_dtmf directly with
    a Python string, bypassing form parsing entirely; no test asserted that
    a POST shaped the way Twilio actually shapes it crosses the route into
    the responder. These tests post real signed Twilio-shaped forms through
    the real Flask app onto a real CuraResponder, and parametrize over the
    dtmf routes and digits so the property — the wire key Twilio uses is
    the key the route reads — is pinned, not one blessed keypress.
    """

    TOKEN = "test-auth-token-abc123"

    def _post(self, path, form, on_med=None, on_help=None):
        from twilio.request_validator import RequestValidator
        from cura.comms.responder import CuraResponder
        from cura.comms import webhook as wh
        responder = CuraResponder(on_medication_confirmed=on_med,
                                  on_help_requested=on_help)
        app = wh.create_app(responder=responder, elder_name="Margaret",
                            auth_token=self.TOKEN)
        sig = RequestValidator(self.TOKEN).compute_signature(
            f"http://localhost{path}", form)
        resp = app.test_client().post(
            path, data=form, headers={"X-Twilio-Signature": sig})
        return resp, responder

    @pytest.mark.parametrize("path,context", [
        ("/voice/checkin-response", "checkin"),
        ("/voice/evening-response", "evening"),
    ])
    @pytest.mark.parametrize("digit", ["1", "2", "9"])
    def test_a_keypress_posted_as_twilio_posts_it_reaches_the_responder(
            self, path, context, digit):
        """Whatever digit Twilio delivers must arrive at handle_dtmf verbatim
        — the digit is Twilio's data, the key spelling is the contract."""
        resp, responder = self._post(path, {"Digits": digit})
        assert resp.status_code == 200
        dtmf = [e for e in responder.response_log if e["type"] == "dtmf"]
        assert [(e["digit"], e["context"]) for e in dtmf] == [(digit, context)], (
            f"Digits={digit} POSTed to {path} never reached handle_dtmf — "
            "the route is not reading the form key Twilio actually sends")
        assert "didn't catch that" not in resp.get_data(as_text=True), (
            "a delivered keypress was answered with the empty-response goodbye")

    def test_pressing_1_at_checkin_records_the_medication_as_taken(self):
        """The confirmation callback must fire from the wire format, not just
        from a direct handle_dtmf call. Under the mutant it never did, and
        Cura kept treating every confirmed dose as missed."""
        confirmed = []
        resp, _ = self._post("/voice/checkin-response", {"Digits": "1"},
                             on_med=lambda: confirmed.append(True))
        assert resp.status_code == 200
        assert confirmed, (
            "she pressed 1 after taking her medications and no confirmation "
            "was recorded")

    def test_pressing_2_at_checkin_reaches_someone_who_can_send_help(self):
        """Pressing 2 is a help request. It must fire on_help_requested from
        a real Twilio-shaped POST; under the mutant she was told goodbye and
        nobody was contacted."""
        helped = []
        resp, _ = self._post("/voice/checkin-response", {"Digits": "2"},
                             on_help=lambda ctx: helped.append(ctx))
        assert resp.status_code == 200
        assert helped, "she pressed 2 for help and nobody was ever contacted"
        assert "didn't catch that" not in resp.get_data(as_text=True)


class TestWebhookRouteContext:
    """Each voice route hands the responder its OWN call context.

    Mutation this closes: webhook.py's checkin-response route
        _responder.handle_dtmf(digits, "checkin")   # correct
        _responder.handle_dtmf(digits, "evening")   # mutant
    survived the suite because no test pinned the context string a route
    passes — the signature-gate tests prove a signed keypress reaches the
    responder, but not which conversation it lands in.

    Under the mutant every morning keypress is answered with evening
    semantics. Press 1 — "I took my medications" — fires an "Elder needs
    something before bed" escalation and never records the medication, so
    the family is woken for nothing while Cura keeps believing the meds
    were missed. Press 2 — "I need help" — is answered "Good. Sleep well
    tonight." and escalates nothing. Press 2 for help reaching nobody is
    the founding defect of this project, reintroduced by one word of
    copy-paste.

    The property, not the instance: a digit means what THIS call's menu
    said it means. So these tests assert on the real callbacks — who was
    actually alerted, what was actually recorded — for both routes, in
    both directions, through the real Flask app with real Twilio
    signatures. The evening test closes the mirrored copy-paste
    ("evening" -> "checkin") the same way.
    """

    TOKEN = "test-auth-token-abc123"

    def _client(self):
        from cura.comms.responder import CuraResponder
        from cura.comms import webhook as wh
        confirmed, alerts = [], []
        responder = CuraResponder(
            on_medication_confirmed=lambda: confirmed.append(True),
            on_help_requested=lambda msg: alerts.append(msg))
        app = wh.create_app(responder=responder, elder_name="Margaret",
                            auth_token=self.TOKEN)
        return app.test_client(), confirmed, alerts

    def _post(self, client, path, form):
        from twilio.request_validator import RequestValidator
        sig = RequestValidator(self.TOKEN).compute_signature(
            f"http://localhost{path}", form)
        return client.post(path, data=form,
                           headers={"X-Twilio-Signature": sig})

    def test_morning_press_2_alerts_a_caregiver(self):
        """On the morning menu, 2 is 'I need help'. It must reach a person.
        Under the mutant she was told to sleep well and nobody was called."""
        client, confirmed, alerts = self._client()
        resp = self._post(client, "/voice/checkin-response", {"Digits": "2"})
        assert resp.status_code == 200
        assert alerts, ("press 2 for help on the morning check-in "
                        "reached nobody")
        assert not confirmed, ("a help request must never be recorded as a "
                               "medication confirmation")

    def test_morning_press_1_records_meds_and_wakes_nobody(self):
        """On the morning menu, 1 is 'I took my medications'. It must be
        recorded — and must NOT page the family. Under the mutant it fired
        an 'Elder needs something before bed' escalation instead, and the
        medication was never recorded, so Cura kept treating it as missed."""
        client, confirmed, alerts = self._client()
        resp = self._post(client, "/voice/checkin-response", {"Digits": "1"})
        assert resp.status_code == 200
        assert confirmed, ("press 1 on the morning check-in never recorded "
                           "the medication")
        assert not alerts, ("press 1 — 'I took my meds' — escalated to the "
                            "family as a help request")

    def test_evening_press_1_asks_family_not_medication(self):
        """The mirror image, so the same copy-paste cannot come back the
        other way round: on the evening menu, 1 is 'I need something before
        bed' — it must alert the family and must NOT be recorded as a
        medication confirmation."""
        client, confirmed, alerts = self._client()
        resp = self._post(client, "/voice/evening-response", {"Digits": "1"})
        assert resp.status_code == 200
        assert alerts, ("press 1 on the evening call — 'I need something' — "
                        "reached nobody")
        assert not confirmed, ("an evening help request was recorded as a "
                               "medication confirmation")


class TestTwiMLResponseRoot:
    """Twilio's TwiML contract requires a single <Response> root element.

    Mutation caught 2026-09: webhook._twiml dropped the <Response> wrapper,
    returning the bare body after the XML declaration. Whenever the body was
    a single element the document was still well-formed XML, so
    test_webhook_twiml_stays_well_formed stayed green -- it checked XML
    validity, not the TwiML contract. But Twilio rejects any reply whose root
    is not <Response>, so every webhook reply -- every keypress, every spoken
    answer -- would have been invalid TwiML. The household experience: Cura
    calls, asks her husband a question, and the call errors out the instant
    he presses a button or speaks. Every interaction dies at the first
    response.
    """

    @pytest.mark.parametrize("text", TestTwiMLEscaping.HOSTILE)
    def test_root_element_is_response(self, text):
        import xml.etree.ElementTree as ET
        from cura.comms import webhook as wh
        root = ET.fromstring(wh._twiml(wh._say(text)))
        assert root.tag == "Response", (
            f"TwiML root must be <Response>, got <{root.tag}> -- Twilio "
            "rejects any document with another root, so the call errors "
            "out the moment the elder responds")

    def test_multi_element_bodies_are_wrapped_in_one_response(self):
        """A Gather body is several sibling elements (the Gather plus the
        no-answer fallback Say). Only the <Response> wrapper makes them one
        document; without it the reply is not even well-formed XML, and the
        inbound-call menu -- the path Margaret's husband uses to reach Cura
        -- dies before the first prompt finishes."""
        import xml.etree.ElementTree as ET
        from cura.comms import webhook as wh
        body = wh._gather("Press 1 if you took your medication.",
                          "/voice/checkin-response")
        root = ET.fromstring(wh._twiml(body))
        assert root.tag == "Response"
        assert root.find("Gather") is not None, \
            "the Gather must be a direct child of <Response>"
        assert root.find("Say") is not None, \
            "the no-answer fallback Say must be a direct child of <Response>"


@pytest.mark.asyncio
class TestCheckinsDialTheElder:
    """Check-in calls must ring the elder's own phone, not a contact's.

    Mutation this closes: voice.py morning_checkin (line 330)
        to_number=elder_phone,   # correct — the elder's own number
        to_number=phone,         # mutant — the emergency-contact fallback

    morning_checkin computes `phone` (first emergency contact, else the
    primary caregiver) purely as a fallback for a profile that has no phone
    of its own, then dials `elder_phone`. The mutant dials the fallback
    unconditionally. Household consequence: every morning the check-in
    rings the daughter — possibly out of state — instead of the elder. She
    never hears her check-in or her medication prompt; the daughter gets a
    confusing recorded call each day; and the call log still shows
    answered=True, so nothing downstream ever notices that the elder was
    never rung.

    It survived because test_morning_checkin asserted only result.answered
    and transcript content — nothing pinned WHO was dialed. These tests pin
    the property: the number the check-in dials is the elder's own, and is
    none of the contacts' numbers. Real ElderProfile, real CuraVoice
    dry-run path — which records into CallResult the exact to_number handed
    to call() — no stubs carrying imagined fields.
    """

    def _contact_numbers(self, profile) -> set[str]:
        nums = {c["phone"] for c in profile.emergency_contacts}
        nums.add(profile.primary_caregiver["phone"])
        return nums

    async def test_morning_checkin_dials_the_elders_own_phone(self):
        voice = CuraVoice(dry_run=True)
        profile = _make_profile()
        result = await voice.morning_checkin(profile)
        assert result.to_number == profile.phone, (
            f"morning check-in dialed {result.to_number!r}, not the elder's "
            f"own phone {profile.phone!r}")

    async def test_morning_checkin_never_dials_a_contact_instead(self):
        """The daughter's phone ringing each morning with the elder's
        medication prompt is the visible half of the failure; the elder
        sitting by a silent phone is the half that matters."""
        voice = CuraVoice(dry_run=True)
        profile = _make_profile()
        result = await voice.morning_checkin(profile)
        assert result.to_number not in self._contact_numbers(profile), (
            "morning check-in dialed an emergency contact / caregiver "
            "number instead of the elder")

    async def test_evening_checkin_dials_the_elders_own_phone(self):
        """The mirrored path, pinned the same way, so the same one-word swap
        cannot land unnoticed in evening_checkin."""
        voice = CuraVoice(dry_run=True)
        profile = _make_profile()
        result = await voice.evening_checkin(profile)
        assert result.to_number == profile.phone, (
            f"evening check-in dialed {result.to_number!r}, not the elder's "
            f"own phone {profile.phone!r}")
        assert result.to_number not in self._contact_numbers(profile)


class TestCallStatusReachesTheStatusRoute:
    """Both scheduled calls pointed status_callback at the DTMF handlers, so
    /voice/status never fired and a `no-answer` was posted to a route expecting
    a keypress. Nothing in the system learned a check-in had gone unanswered —
    which is the signal adherence tracking and escalation are built on."""

    def test_both_senders_point_at_the_status_route(self):
        import ast
        from pathlib import Path
        repo = Path(__file__).resolve().parent.parent
        tree = ast.parse((repo / "cura/__main__.py").read_text())
        for fn in ("do_morning", "do_evening"):
            node = next(n for n in ast.walk(tree)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and n.name == fn)
            cbs = [k.value.value for c in ast.walk(node)
                   if isinstance(c, ast.Call)
                   for k in c.keywords
                   if k.arg == "status_callback" and isinstance(k.value, ast.Constant)]
            assert cbs, f"{fn} sets no status_callback"
            for cb in cbs:
                assert cb == "/voice/status", \
                    f"{fn} posts call status to {cb!r}, which expects a keypress"

    def test_the_status_route_is_not_the_response_route(self):
        """They parse different payloads. Twilio posts CallStatus, not Digits."""
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent
               / "cura/comms/webhook.py").read_text()
        i = src.index('@app.route("/voice/status"')
        block = src[i:i + 1600]
        assert "CallStatus" in block
        assert "no-answer" in block, "the route cannot tell unanswered from done"
