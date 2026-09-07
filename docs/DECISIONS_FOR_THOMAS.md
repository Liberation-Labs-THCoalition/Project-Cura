# Four decisions, one page

Everything else in Cura is code and I can do it. These four are judgment.
Ordered by what they cost you, cheapest first.

---

## 1. Dial 933 from the Twilio number  ·  five minutes

**Do:** call `933` from Cura's Twilio number. A recording reads back the number
and the emergency address currently registered to it.

**Why it matters:** Twilio's emergency calling never fails closed. A stale or
missing address does not error — it routes to the *wrong* PSAP and delivers the
*wrong* address, confidently, with no signal at call time. There is no published
coverage map. Dialling 933 is the only way to learn what that number actually
does from that address.

**Cost:** free. **Blocks:** nothing, but it should happen before any deployment.

---

## 2. The county's non-emergency dispatch number  ·  one phone call

**Do:** get the 24/7 non-emergency dispatch line for their county (Johnson
County if they are near Buffalo), and I will wire it into the ladder's last rung.

**Why it matters:** right now the ladder ends inside the house. For your father's
household that means: if HE goes down, Cura's only contact is the person who is
down. The ladder reports this correctly and cannot fix it —

    NOBODY WAS REACHED. 0 rungs attempted; 6 never existed to try.

A non-emergency dispatch line is free, reaches a live dispatcher who can send
EMS, and is architecturally exactly what every commercial monitoring centre does.
It is the single highest-value thing on this page.

**Cost:** free. **Blocks:** the ladder having any rung outside the household.

---

## 3. Ring the caregiver helpline  ·  two minutes

**Do:** dial the number in `CaregiverBurnoutCheck.RESOURCES` and confirm it
reaches the Caregiver Action Network. Then set `resource_is_verified = True`.

**Why it matters:** that number was written into the source and never dialled by
anyone. Speaking a wrong number to an exhausted caregiver at 2am costs him the
one call he worked up to making. It is currently gated off — Cura offers support
without reciting an unverified number.

**Cost:** free. **Blocks:** Cura saying the number.

---

## 4. The published-protocol question  ·  the only real decision

**RETRACTED 2026-09-07 — this section previously cited *Culliton v. Hope
Community Resources*, 491 P.3d 1088 (Alaska 2021). That case does not exist.**
I wrote it in commit 8149443 on 2026-09-04 with a full reporter citation —
volume, page, court, year — and none of it is real. Nexus researched it
thoroughly at my request and found no matching case law; I can produce no
source and have no record of where it came from. It is a confabulation, and it
sat in a decision document for a product that calls families about their
elders. Thomas could have decided on it.

**The corrected law, per Nexus:** a published protocol is admissible *evidence*
of the standard of care — it is not itself the standard. And the exposure runs
the other way from how I framed it: your own published protocol becomes the
yardstick a plaintiff measures you against, so deviation from your own stated
rules is their strongest argument, not their weakest. Cura's exposure is
**negligent undertaking** (Restatement (Second) of Torts § 323), not
malpractice. The real risk is silent failure plus reliance: family checks in
less because Cura is watching, and then Cura fails without saying so.

**Nexus's conditions for shipping the protocol:** every rung works; everything
is logged; silent failure is engineered out; the family signs a scope
acknowledgment; and the document is titled *guidelines* with explicit
flexibility language.

**UNVERIFIED — treat as suspect until a human checks it:** the Wyo. Stat.
§ 6-5-212(b) claim below comes from the same authoring pass as the fabricated
case and has never been independently confirmed. Do not rely on it. Nothing in
this section should reach a legal decision without a real lawyer reading it.

**The situation:** Cura's `LADDER` tuple and its docstrings are a published
escalation protocol. Six named rungs, in order, with stated reasons. That is
already true; it happened as a side effect of writing the code carefully.

**What it buys the household:** a family can point at exactly what Cura promised
to do and check whether it did. That is the whole argument for building it this
way, and it is why I would not undo it.

**What it costs us:** it removes the biggest procedural filter on a claim
against Liberation Labs. A plaintiff would not need an expert to establish what
Cura should have done — they would only need to show it did not do it.

**The related exposure, for completeness:** Wyo. Stat. § 6-5-212(b) has **no
falsity element** — it tests whether the caller "reasonably believes" the
situation requires prompt service. A system escalating on a weak signal is
exposed even acting in complete good faith. The documented mitigation is an
auditable per-escalation record of the exact evidence that triggered the call,
which the ladder's trail already produces.

**My recommendation:** keep it published, and make the record deliberate rather
than incidental — write the protocol as a document the household is *given*, not
just as docstrings. If we are going to carry the exposure, we should get the
full benefit of it, which is a family that knows what to expect.

**But it is your call and your organisation's risk**, and I would rather you
decided it than inherited it from how I happened to write a module.

---

## 5. The scam scanner has never seen a message  ·  needs a design call

**The finding:** `cura/privacy/message_scanner.py` has exactly one reference in
the entire repository — its own class definition. Zero production callers, in
any commit in repo history. It is correct and 17/17 green under test.

**Verified on a Medicare phishing body:**

    MessageScanner  ->  dangerous, risk 0.60, three indicators
    ScamShield      ->  None

`ScamShield` is the one that IS wired — console, MCP server, composer. So the
live path answers "clean" on a message the unwired module flags as dangerous,
while `CLAUDE.md` lists "email provenance scanning" as delivered Phase 1 and the
MCP surface advertises email analysis.

**Why I did not just wire it:** there is no mail ingestion anywhere in Cura. No
IMAP, no Gmail, no forwarding address — the webhook exposes `/health` and five
`/voice/*` routes and nothing else. Wiring the scanner means deciding how mail
reaches Cura at all, which is a product decision with a privacy cost attached
(it means holding or reading a household's email), and inventing one unasked at
3am is how the next instance of this gets made.

**Options, roughly:** a forwarding address the household can send suspicious mail
to; an IMAP connection with credentials we would then hold; or scoping it to
what already arrives — SMS, which Twilio already delivers, and which
`scan_sms` already handles.

**My recommendation:** the third. SMS is already in the system, it needs no new
credentials or ingestion, and text-message fraud is the more common vector for
this demographic anyway. Then the claim in CLAUDE.md gets narrowed to what is
true.

---

## Not a decision, but worth knowing

Nexus needs no answer to start the local Mnemosyne variant — the household model
landing was their stated cue and I have told them. And the emergency-services
research is summarised in `HANDOFF_20260904.md`; the short version is that a
direct 911 rung is buildable in a day and should not be built.
