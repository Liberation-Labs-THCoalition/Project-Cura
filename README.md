# Cura — A Faithful Companion for Aging at Home

Cura (*cura fidelis* — faithful care) is a phone-based companion for elderly people living independently. She calls to check in, reminds about medications, warns about dangerous weather, helps spot scams, and makes sure family gets the call when something's wrong.

No app to install. No tablet to learn. Just a phone that rings.

---

## What Cura Does

**Every morning and evening**, Cura calls your loved one:

- "Good morning, Margaret. How are you feeling today?"
- "It's time for your Lisinopril and Metformin."
- "It's going to be 95 degrees today — please drink extra water."
- "Has Whiskers been fed?"

**She protects against scams** — the #1 financial threat to elders:

- Gentle safety tips woven into conversation ("The IRS will never call demanding payment")
- Asks periodically: "Has anyone asked you for money recently?"
- Scans incoming email for phishing (spoofed Medicare, fake Amazon, etc.)
- If something's wrong, she reassures and alerts the family

**She keeps the mind active:**

- "Yesterday we talked about your garden. Do you remember what you told me?"
- "Can you name three fruits that start with B?"
- Offers to read books aloud during check-ins

**She watches out for the caregiver too:**

- Weekly call to the primary caregiver: "How are YOU doing, Sarah?"
- Because nobody checks on the people doing the checking

**When something goes wrong**, Cura calls and texts every emergency contact immediately.

---

## For Families: Getting Started

### What You Need

1. **A phone number for your loved one** — landline or cell, either works
2. **A Twilio account** — this is the service that makes the phone calls ($1/month or less for daily check-ins). Sign up at [twilio.com](https://www.twilio.com)
3. **A computer to run Cura on** — can be a cheap Linux machine, a Raspberry Pi, or a cloud server

### Step 1: Install

```bash
# Download Cura
git clone https://github.com/Liberation-Labs-THCoalition/Project-Cura.git
cd Project-Cura

# Install Python dependencies
pip install -r requirements.txt
```

### Step 2: Set Up Your Loved One's Profile

Create a file called `my_elder.py` (or whatever name you like):

```python
from cura.pulse.eldercare_pulse import ElderProfile

margaret = ElderProfile(
    name="Margaret Chen",
    preferred_name="Margaret",       # What she likes to be called
    phone="+15551234567",            # Her phone number

    medications=[
        {"name": "Lisinopril", "time": "morning"},
        {"name": "Metformin", "time": "morning"},
        {"name": "Amlodipine", "time": "evening PM"},
    ],

    emergency_contacts=[
        {"name": "Sarah Chen", "phone": "+15559876543", "relation": "daughter"},
        {"name": "Tom Chen", "phone": "+15559876544", "relation": "son"},
    ],

    primary_caregiver={
        "name": "Sarah Chen",
        "phone": "+15559876543",
    },

    address="123 Elm Street, Springfield, IL",

    morning_time=8,      # When she wakes up (24-hour clock)
    evening_time=20,     # When she winds down
)
```

You know your loved one best. Set the times to match their routine.

### Step 3: Configure Twilio

Set these environment variables (or put them in a `.env` file):

```bash
export TWILIO_ACCOUNT_SID="your_account_sid"
export TWILIO_AUTH_TOKEN="your_auth_token"
export TWILIO_PHONE_NUMBER="+15550001234"   # Your Twilio number
```

You'll find these values in your Twilio dashboard after signing up.

### Step 4: Test It

Before going live, run in dry-run mode to see what Cura would say:

```bash
python -m pytest tests/ -q    # Make sure everything works
```

```python
from cura.comms.voice import CuraVoice
from cura.pulse.eldercare_pulse import EldercarePulseConfig
from cura.pulse.checkin_composer import CheckinComposer

# Dry run — no actual calls
voice = CuraVoice(dry_run=True)
config = EldercarePulseConfig(margaret)
composer = CheckinComposer()

# See what a morning check-in looks like
checkin = composer.compose_morning(config, weather={"temp_f": 85})
for msg in checkin.all_messages:
    print(f"  Cura: {msg}")
```

When you're happy with it, remove `dry_run=True` and Cura will make real calls.

---

## For Elders: What to Expect

**Cura will call you twice a day** — once in the morning and once in the evening. She'll:

- Ask how you're feeling
- Remind you about your medications
- Sometimes ask you a fun question or share a safety tip
- Ask if you need anything

**You're always in control:**

- Don't want to talk? Just don't answer. Cura will try again later.
- Want to stop the calls? Tell your caregiver and they'll pause them.
- Want to change when Cura calls? Your caregiver can adjust the times.

**If someone asks you for money or personal information**, tell Cura about it during your next check-in. She'll help you figure out if it's a scam and let your family know.

**Cura will never:**
- Ask for your bank account or Social Security number
- Tell you to send money to anyone
- Share your health information with insurance companies
- Replace your doctor's advice

She's just a friendly voice making sure you're okay.

---

## Optional Features

These are extras you can add if you want them. None are required.

### Weather Alerts

Cura can warn about dangerous heat, cold, or ice. No API key needed:

```python
from cura.integrations.weather import WeatherService

# Springfield, IL coordinates
weather = WeatherService(latitude=39.7817, longitude=-89.6501)
current = await weather.get_current()
# Returns: {"temp_f": 95, "condition": "Clear", ...}
```

### Book Reading

Load an e-book and Cura will read passages during check-ins:

```bash
pip install EbookLib    # For EPUB files
pip install PyMuPDF     # For PDF files
```

```python
from cura.integrations.ebook_reader import EbookParser
from cura.pulse.daily_enrichments import BookReader

title, text = EbookParser.parse("/path/to/book.epub")
reader = BookReader()
reader.load_text(title, text)
# Cura will offer to read during evening check-ins
```

### Voice Analysis

Detect changes in vocal patterns that might indicate illness or distress:

```bash
pip install opensmile    # Best quality (non-commercial use)
# or
pip install librosa      # Alternative (any use)
```

### Local Text-to-Speech

Generate audio locally instead of using Twilio's cloud TTS:

```bash
pip install piper-tts
```

---

## Privacy

Cura is built privacy-first:

- **Health data is never shared with insurance companies.** Period.
- **Email scanning checks sender authenticity, not content.** Cura looks at who sent it and whether the links are real — she doesn't read your mail.
- **The elder can disable any feature at any time.** Say "stop checking my email" and it stops.
- **Scanned message content is processed in memory and discarded.** Only the safety verdict is kept.
- **Family sees only what the elder authorizes.** Cura respects boundaries.

---

## Cost

Cura itself is free and open source.

The only cost is Twilio for phone calls — roughly **$1-2 per month** for two daily check-ins. That's less than a cup of coffee for daily peace of mind.

---

## Getting Help

- **Something's not working?** Open an issue at [github.com/Liberation-Labs-THCoalition/Project-Cura/issues](https://github.com/Liberation-Labs-THCoalition/Project-Cura/issues)
- **Want to contribute?** We welcome pull requests. Read `CLAUDE.md` for project context.
- **Questions about eldercare technology?** Reach out to the team at Liberation Labs.

---

## About

Built by [Liberation Labs / TH Coalition](https://github.com/Liberation-Labs-THCoalition). Named for the Roman spirit Cura, who shaped humanity from clay and was granted the right to tend them throughout their lives.

Because she shaped them with concern.

*The technology doesn't replace family. It makes sure family gets the call.*
