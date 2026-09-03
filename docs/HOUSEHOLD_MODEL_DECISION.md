# The household model — one page, for a fresh brain

Workflow `cura-household-model` (wf_bb5f7ac4-fc3): 10 agents, 3 designs, all
scored **7/10**. No winner. That is useful rather than disappointing — the
disagreements are where the decisions are.

Full output: `/tmp/claude-1000/-home-asdf/ff2cec31-eb06-4aaf-b8ad-01993f849fc9/tasks/w6qdxmk3x.output`

---

## 1. The blocker, and it is live right now

**The real household cannot start Cura.** Verified:

```
escalation_readiness(Margaret, phone="", caregiver=Ray +13075550199)
  -> ['the person Cura calls has no phone number Cura can dial']
  -> _build_responder() calls sys.exit(1)
```

This is a consequence of MY hardening on 2026-09-02. I made the gate reject
undialable numbers, which is correct when a skipped question produces `"+"`, and
wrong when the truth is *she cannot be called at all*.

The gate encodes the assumption the whole household model exists to remove: that
the cared-for person is the person Cura calls. **Do not loosen it casually** —
two of three judges flagged exactly this as the riskiest step in their designs
("a deliberate loosening of a safety gate, and I may have drawn the line
wrong"). The right fix is the household model, not a bypass.

## 2. All three designs had the SAME safety flaw

Independently. This is the most valuable result of the exercise.

| design | flaw |
|---|---|
| 1 | `contacts_for` excludes by `member_id`, dials by phone number; a shared rural landline defeats it |
| 2 | `responders_for` ignores `ContactPolicy` entirely |
| 3 | `responders_for` never consults `Initiative` |

**All three would call Margaret for help.** The woman who cannot answer a phone
becomes the emergency contact.

Three designers separated "may Cura call this person for check-ins" from "may
Cura call this person for help", and all three forgot to apply the permission to
the second. That is not a flaw in any one design — it is a trap in the shape of
the problem.

**Constraint for whatever we build: ONE permission check, consulted by every
dial site. Not two.** If the answer to "may Cura call this person" lives in two
places, they will drift, and the drift is silent.

## 3. What all three agree on — the actual consensus

Every design, independently:

- **Roles are DERIVED from relationships, never stored on a person.** Ray is
  call-target, subject, and caregiver at once, and none can contradict the
  others because none is separately stored. Kills the drift already visible at
  `wizard.py:387-395`.
- **Outreach permission is a four-state enum, not a bool**, with UNKNOWN a real
  recorded state that schedules nothing and gets reported. Directly mirrors
  `medication_slots` -> silence + `unknown_timing_medications`.
- **Separate "who is called" from "who the call is about."**
- **Split the readiness gate**: household-blocking vs per-person-reportable.
  This is what makes the sole-caregiver household configurable at all.

And design 1's structural idea, verified by its judge by actually running it:

- **Keep `ElderProfile` as a PROJECTION.** `profile_for(member_id)` makes
  `voice.py`, `escalation.py`, `checkin_composer.py` and `daily_enrichments.py`
  household-correct with **no edits to any of them**. Blank `phone` in the
  projection when outreach is NEVER, while keeping the number on the Member as a
  fact. Verified: `profile_for('margaret').phone == ''`, and the composer
  produced both registers in one line with zero composer changes.

That is the migration path: a projection, not a rewrite.

## 4. Blocked on Thomas

1. **The keypad line.** Cura never says a key exists — verified, neither
   composer mentions one. So `<Gather>`, the action URL and escalation are all
   built and all unreachable. Every call? Only evening? Different words?
2. **Which model**, or the synthesis: design 1's projection + designs 2/3's
   derived roles + one unified permission check. (This is my recommendation.)
3. **Mnemosyne shape.** Not wired into Cura at all. Must run on the box. Is
   there a local-deployable form, or is that new work for Nexus?
4. **Passive monitoring ordering.** You said Dad needs monitoring for Mom *as
   part of* helping him. If sensors are load-bearing for stage 1, the ordering
   changes.
5. **`Outreach.UNKNOWN` severity.** A missing preference about a fifth person
   currently blocks the whole household. The readiness list needs severity; it
   has none.

## 5. Overnight, done

- `_report_call` read `success`/`sid`; `CallResult` has `answered`/`call_sid`.
  Every successful check-in printed FAILED. Mine, from the night before.
- `gui._norm_phone("")` still returned `"+"` — I unified the validators and left
  the normalisers divergent, in the same file, in the commit that said "one rule
  now". The window is what the packaged app launches.
- `recent_observations(days=)` computed a cutoff and never compared it. A worry
  from four months ago was handed to Cura as "Recent conversations".
- `_default_config_path` returns None for zero configs AND for two, and told a
  household that had set up two people that Cura "isn't set up yet".
- `HomeSafetyAssessment.get_summary()` always said "no concerns identified",
  because `record_concern` has no caller — and **a test pinned the lie**,
  asserting a fresh assessment reports clean.

361 passing, up from 333. Every fix mutation-verified.

## 6. Still open, not touched

`/voice/status` has no caller. Weather never reaches a real call. `cura
rehearse` cannot show what will actually be heard (`random.random()` rolls in
the composer). `CaregiverBurnoutCheck` and `CaregiverSummaryBuilder` are written
and tested and have never been spoken — the words for "Cura asks after your
father" are already in the repo.
