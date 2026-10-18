# CLAUDE.md — Project Cura

## What Is Cura

Cura (*Cura fidelis* — faithful care) is an AI eldercare companion. It unifies seven disconnected eldercare silos — emergency response, medication management, remote monitoring, fall detection, benefits navigation, caregiver coordination, and social companionship — into one intelligent, privacy-first system.

Named for the Roman spirit who shaped humanity from clay and was granted the right to tend them throughout their lives. Because she shaped them with concern.

The technology doesn't replace family. It makes sure family gets the call.

## Architecture

What runs (checked against the code 2026-10-17):
- **Check-ins:** `cura run` schedules the morning and evening calls with APScheduler; `CheckinComposer` writes what
  is said; `CuraVoice` places the call through Twilio.
- **Help and escalation:** `cura webhook` hands each spoken reply to `CuraResponder`: help words first, scam words
  second, a pending question third. Help goes up the ladder in `cura/comms/ladder.py`, calling only the household
  members `household.may_call` allows, then any outside rung (a monitoring service or dispatch line).
- **What Cura is not handling:** `cura/readiness.py::readiness_gaps()` lists it in plain lines for the caregiver.
  Showing it in `cura rehearse` and `cura_health` comes next (rollout spec C2, C3).
- **Values:** `config/VALUES.json` states Cura's values; no code reads it at run time.
- **Kintsugi:** not used. (An earlier version of this file said Cura was built on Kintsugi primitives; it never was.)

```
Phone/SMS (Twilio) ←→ Check-in scheduler ←→ Sensor Layer
                         ↓                  ↓
                   Intelligence      Wearable Bridge
                    (patterns,        (BLE vitals)
                     anomalies)
                         ↓
                   Coordination
                    (family dashboard,
                     caregiver alerts,
                     crisis escalation)
```

## Key Directories

```
cura/
  pulse/       Eldercare Pulse config, daily enrichments, check-in composer
  sensors/     Browser sensor integration (accelerometer, mic, camera, touch)
  benefits/    Medicare/Medicaid/VA portal navigation
  comms/       Twilio voice/SMS + family notification
  privacy/     Scam shield, message scanner, consent tracking, HIPAA compliance
  integrations/ Open source wrappers (weather, ebook, TTS, voice analysis)
  dashboard/   Family/caregiver web dashboard
  memory/      Elder profile, pattern history, medication tracking
config/        VALUES.json templates for eldercare
tests/         Test suite (799 tests)
docs/          Architecture spec, regulatory notes
```

## Phase 1 MVP: Phone Companion

No sensors, no app, no PWA. Just phone calls and texts.
- Morning + evening check-in calls via Twilio
- SMS medication reminders
- Daily enrichments (hydration, nutrition, weather, cognitive exercises, pet care, movement, reading)
- Scam defense (education tips, screening questions, keyword detection, email provenance scanning)
- Caregiver burnout check-ins (weekly)
- Home safety assessment (periodic questions over several weeks)
- Benefits guidance (conversational)
- Family dashboard (web)
- Crisis: alert family, they call 911

## Ethics (Non-Negotiable)

- Elder's autonomy is paramount — they can refuse any check
- Health data never shared with insurance companies
- No monetization of biometric or behavioral data
- Ongoing consent, revocable at any moment
- Family sees only what elder explicitly authorizes
- Never substitute for professional medical advice
- Dignity in all interactions — no infantilizing language
- Cost: $0 for mission-aligned organizations

## Regulatory Positioning

General wellness device. Detect + alert + coordinate.
Never diagnose. Never prescribe. Never call 911 directly.

## Team

- **CC (Coalition Code)** — Architecture
- **Thomas Edrington** — Project direction
- **Liberation Labs / TH Coalition** — Parent organization
- Clinical advisor, eldercare professional, legal review: TBD
- Elder beta testers: essential before any launch

## Running Tests

```bash
cd /home/asdf/Project-Cura
.venv/bin/python -m pytest tests/ -q      # THE VENV IS NOT OPTIONAL

# Run it any other way and the verdict changes. On 2026-09-08 the suite
# reported 18 failures under a different interpreter -- flask and
# pytest-asyncio missing -- including all seven webhook signature-gate tests,
# which assert that an unsigned Twilio POST is rejected. Nothing was broken;
# they had simply never run. A suite whose answer depends on which python is
# on PATH is a suite that can report anything.
#   .venv/bin/pip install -e '.[test]'    # if pytest is missing
# Expected: 799 passed.
```
