# Project Cura — Audit

Date: 2026-07-07
Scope: full read of `cura/`, `tests/`, `config/`, `docs/`, `README.md`, `CLAUDE.md`, `requirements.txt`, git history.
Method: read every source file, ran the test suite, cross-checked docstrings/README claims against actual imports and call graphs.

## Verdict

The core phone-companion loop (Twilio voice/SMS, check-in composition, scam shield, memory, wearables) is solid, well-tested, and true to the project's ethics. The main risks aren't in what's built — they're in **what's built but not connected**, **what's documented but doesn't exist**, and **a few facts that have drifted** (test count, package currency, external API assumptions). Nothing here blocks continued development; several items should block a first real deployment to an elder.

## 1. Facts that have drifted

- **Test count is stale everywhere it's cited.** `CLAUDE.md` says "80 tests", the audit brief said 117, actual is **142 passed** (`python3 -m pytest tests/ -q`). Update `CLAUDE.md`'s directory listing.
- **`docs/` is an empty directory.** `CLAUDE.md` describes it as "Architecture spec, regulatory notes" — neither exists. Either write them or stop advertising them.
- **`cura/benefits/` and `cura/dashboard/` are empty packages** (just `__init__.py`). README and CLAUDE.md both describe live features here ("Medicare/Medicaid/VA portal navigation", "family dashboard (web)"). These are Phase-1-MVP-adjacent promises with zero implementation — worth explicitly marking as "not started" in the README rather than implying they exist, or removing from the Phase 1 feature list until built.
- **No `pyproject.toml` / `setup.py` exists**, but the README instructs `pip install cura[weather]`, `cura[ebook]`, `cura[voice]`, `cura[tts]`, `cura[all]`. None of these extras are defined anywhere — that install command fails today. Either add packaging metadata with those extras or change the README to `pip install -r requirements.txt` plus the individual per-feature `pip install` lines that are already given.
- **`requirements.txt` is missing two runtime dependencies that the code actually imports:** `flask` (used in `cura/comms/webhook.py`, the entire Twilio-facing HTTP layer) and `apscheduler` (used in `cura/__main__.py`'s `run` command). Both are lazily imported with a graceful fallback, so tests pass without them, but a fresh `pip install -r requirements.txt` leaves `cura run` and `cura webhook` non-functional out of the box. Add both (Flask as core, APScheduler as core or clearly-flagged optional).
- **`cura/integrations/weather.py` docstring says `pip install openmeteo-requests requests-cache`**, but the implementation doesn't use either package — it calls Open-Meteo directly over raw `aiohttp`. Harmless (the actual code is fine, arguably simpler), but the docstring will send a contributor down the wrong path.

## 2. Built but not wired in (integration debt)

Three meaningfully-sized features exist, are self-contained, and are never imported by anything in the live call/text/console flow:

- **`cura/tools/boundary_guardian.py` (`ElderGuardian`) — elder abuse detection.** This is directly on-mission (VALUES.json lists caregiver/financial abuse detection as a core ethic) and was the headline of the most recent commit ("Add bash executor and elder abuse guardian"), but nothing in `console.py`, `responder.py`, or `checkin_composer.py` instantiates or calls it. Today, a caregiver-abuse disclosure during a call gets no different handling than any other statement. This is the highest-value gap to close — the module is done, it just needs one call site in `CuraResponder.handle_speech` / `console.run_interactive` alongside the existing scam-shield check.
- **`cura/pulse/daily_enrichments.py:SocialMatchmaker`** — fully implemented and unit-tested (`tests/test_daily_enrichments.py::TestSocialMatchmaker`), but never imported by `CheckinComposer` or anything else. Dead weight until either wired in or removed.
- **`cura/tools/bash_executor.py` (`BashExecutor`)** — sandboxed shell execution lifted from the Kintsugi companion scaffold. There is no plausible reason an elder-facing phone companion needs to run arbitrary shell commands; it isn't referenced anywhere in `cura/`. This looks like boilerplate carried over from the Kintsugi template rather than a Cura feature. Recommend removing it — an unused general-purpose command executor sitting in an eldercare privacy-first codebase is attack surface with no offsetting benefit, and it will read as suspicious in any security review.

## 3. Correctness / accuracy issues worth fixing

- **`CuraVoice.crisis_alert` docstring claims contacts are notified "in parallel"** (`cura/comms/voice.py:313-350`) but the implementation `await`s `send_sms` then `call` sequentially inside a `for` loop over `profile.emergency_contacts`. For the VALUES.json target of "fall-to-family-notification under 5 minutes," this is very unlikely to matter for 2-3 contacts, but it's inaccurate as documented and trivial to fix with `asyncio.gather`.
- **TwiML `<Say voice="..." rate="...">` — verify the `rate` attribute is honored.** Both `cura/comms/voice.py` and `cura/comms/webhook.py` set `rate="slow"` as a literal attribute on `<Say>`. Twilio's documented mechanism for controlling Polly speech rate is SSML `<prosody rate="...">` nested *inside* `<Say>`, not a bare `rate` attribute on the element itself. This should be checked against current Twilio TwiML docs — if `rate` isn't a real `<Say>` attribute, every call is silently playing at default speed, which directly undermines the "speech rate: slow for elderly listeners" design intent called out in the module docstring.
- **Fitbit integration risk.** `cura/sensors/fitbit_provider.py` depends on `python-fitbit`, which has seen minimal maintenance for years, and on Fitbit's intraday-time-series endpoints. Fitbit has restricted intraday API access for new "Personal" app registrations for a while now (elevated/partner access is required to pull another person's intraday heart-rate data) — the README's "register a Personal app, get your tokens" walkthrough may no longer work for a caregiver setting this up fresh in 2026. Worth a live smoke test against a real Fitbit dev account before telling families this is a supported path; the Gadgetbridge tier (no cloud API, reads a local SQLite export) is the more future-proof of the two and could become the recommended default instead of Fitbit.

## 4. Test coverage gaps

142 tests pass, and coverage of the core domain logic (scam shield, message scanner, memory, wearable analyzer, check-in composer, pulse config, responder, caregiver summary) is genuinely good. Gaps:

- **`cura/comms/webhook.py` has zero test coverage.** This is the actual Flask/Twilio HTTP boundary — the code path that runs in production when Twilio hits the server. Nothing exercises the five routes (`/voice/checkin-response`, `/voice/evening-response`, `/voice/inbound`, `/voice/inbound-response`, `/voice/inbound-chat`) or the TwiML string-building helpers. Flask's test client makes this cheap to add.
- **`cura/tools/boundary_guardian.py` and `cura/tools/bash_executor.py`** have no tests — consistent with them being unwired/unused (§2).
- Minor: `tests/test_scam_shield.py` contains `TestMessageScannerIntegration`, which tests `cura/privacy/message_scanner.py`. Coverage is fine, but the file name doesn't match the module under test — a `tests/test_message_scanner.py` split would make coverage legible at a glance.

## 5. Privacy/security note (given the "privacy-first, HIPAA-grade" positioning)

The README's setup instructions have the caregiver put the Twilio `account_sid` and `auth_token` in plaintext inside `margaret.json` alongside the elder's name, phone, address, and medications. That config file also isn't gitignored-by-default guidance in the README (only `.gitignore` in the repo itself is scoped to the repo, not to a caregiver's deployment). Given the project's own ethics bar ("HIPAA-grade privacy"), it's worth adding a documented option to source Twilio credentials from environment variables instead, and a note in the README warning caregivers not to commit or share the config file.

## 6. What's working well (don't touch)

- The scam/fraud modules (`scam_shield.py`, `message_scanner.py`) are thorough, well-scoped ("provenance not surveillance"), and well-tested — this is the strongest part of the codebase.
- `companion_memory.py` — the JSON-file-per-elder, no-cloud design is a genuinely good privacy default and matches the stated ethics.
- `CheckinComposer`'s enrichment-selection design (max 3 per check-in, priority-sorted) is a thoughtful guard against overwhelming an elder.
- Dry-run support is threaded consistently through `CuraVoice`, `FitbitProvider`, and `GadgetbridgeProvider` — good for local testing without live credentials.
- Ethics encoded in `config/VALUES.json` (asymmetric risk toward false alarms, elder autonomy overrides caregiver preference, no insurance data sharing) are actually reflected in the code's behavior, not just aspirational.

## Suggested priority order

1. Wire `ElderGuardian` into `CuraResponder.handle_speech` and `console.run_interactive` — highest mission alignment, code already exists.
2. Add `flask` and `apscheduler` to `requirements.txt`.
3. Add webhook route tests (Flask test client).
4. Verify Twilio `<Say rate="...">` actually works; switch to SSML `<prosody>` if not.
5. Fix `crisis_alert` to actually notify contacts concurrently.
6. Decide fate of `bash_executor.py` and `SocialMatchmaker` — wire in or delete.
7. Reconcile README/CLAUDE.md claims (test count, `docs/`, `benefits/`, `dashboard/`, packaging extras) with what actually exists.
8. Smoke-test the Fitbit onboarding flow against a real 2026 developer account before recommending it to families.
