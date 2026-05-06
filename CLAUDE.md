# CLAUDE.md — Project Cura

## What Is Cura

Cura (*Cura fidelis* — faithful care) is an AI eldercare companion built on the Kintsugi Engine. It unifies seven disconnected eldercare silos — emergency response, medication management, remote monitoring, fall detection, benefits navigation, caregiver coordination, and social companionship — into one intelligent, privacy-first system.

Named for the Roman spirit who shaped humanity from clay and was granted the right to tend them throughout their lives. Because she shaped them with concern.

The technology doesn't replace family. It makes sure family gets the call.

## Architecture

Built on Kintsugi Engine primitives:
- **Pulse** — self-modifying heartbeat for daily check-ins + continuous monitoring
- **BDI** — beliefs about the elder's health/patterns, desires from care goals, intentions from active care plans
- **EFE** — health risk-weighted decision-making
- **VALUES.json** — HIPAA-grade privacy, ongoing consent, dignity-preserving
- **Comms Dispatcher** — phone calls (Twilio), SMS, family dashboard
- **Shield Module** — maximum privacy enforcement

```
Phone/SMS (Twilio) ←→ Pulse Engine ←→ Sensor Layer
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
tests/         Test suite (80 tests)
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

- **CC (Coalition Code)** — Architecture, Kintsugi integration
- **Thomas Edrington** — Project direction
- **Liberation Labs / TH Coalition** — Parent organization
- Clinical advisor, eldercare professional, legal review: TBD
- Elder beta testers: essential before any launch

## Running Tests

```bash
cd /home/asdf/Project-Cura
python -m pytest tests/ -x -q
```
