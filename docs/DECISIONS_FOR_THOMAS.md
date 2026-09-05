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

**The finding:** *Culliton v. Hope Community Resources*, 491 P.3d 1088 (Alaska
2021) — failing to follow a **written escalation protocol** is ordinary
negligence, and **no expert testimony is required** to establish the standard of
care. Once a protocol is published, that protocol *is* the standard.

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

## Not a decision, but worth knowing

Nexus needs no answer to start the local Mnemosyne variant — the household model
landing was their stated cue and I have told them. And the emergency-services
research is summarised in `HANDOFF_20260904.md`; the short version is that a
direct 911 rung is buildable in a day and should not be built.
