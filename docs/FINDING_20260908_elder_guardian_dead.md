# The elder-abuse guard has never been able to fire

**Found:** 2026-09-08, by a cardinality sweep over recorded fields
**Severity:** safety-critical, in the protective half of Cura
**Status:** NOT FIXED. Made loud, deliberately not patched. See "Why I stopped."

---

## What is dead

`cura/tools/boundary_guardian.py` — `ElderGuardian`, the module whose docstring
says it watches for financial exploitation, verbal abuse, isolation, medication
coercion and coached speech.

It is dead twice over, and either alone would be enough.

**1. Zero production callers.** No module imports it. Not `comms/responder.py`,
not `pulse/checkin_composer.py`, not `cura_mcp_server.py`. There was no test
file. The class has never run.

**2. Even wired, it could not fire.** `assess(self, message, metadata)` never
reads `message`. The elder's own words are the first parameter and the body
never touches them. Every branch reads a metadata key, and of those keys:

| key | producers in the repo |
|---|---|
| `scam_detected` | 2 — both in `cura_mcp_server.py`, returning it to an MCP client, neither routing it to any guardian |
| `abuse_detected` | **0** |
| `isolation_pattern` | **0** |
| `abuse_severity` | **0** |
| `scam_severity` | **0** |

All three branch conditions are permanently absent, so `assess()` returns `None`
for every possible input and `process()` returns the constant
`{"action": "continue", "alert_level": "monitor"}`.

**3. The thresholds are decorative.** `alert_family_threshold` (0.7) and
`alert_authorities_threshold` (0.9) are declared and read by nothing. Escalation
uses a hardcoded `0.9` at the comparison site. A deployer who lowers the bar for
a fragile household changes nothing, silently.

## What is NOT affected

**The scam-defense half is real.** `ScamShield` is wired into
`checkin_composer.py` at :109 and exercised by `tests/test_scam_shield.py`. Scam
education, screening questions, keyword detection and email provenance all work.

What has never worked is **caregiver abuse, coercion, and isolation detection.**

## Why this matters more than the count suggests

From the project's own handoff, the household every design call is made for: a
man in his seventies in rural Wyoming, sole caregiver for his wife with
late-stage dementia. Caregiver-abuse detection matters most precisely where the
caregiver is isolated and under strain — which is this household exactly, and
which is the case the module was written for.

## Why I stopped instead of fixing it

I could have wired it tonight. I did not, and the reason should survive me.

Detecting caregiver abuse from message text is not an engineering problem with a
correct answer. A false positive means telling a family that the person keeping
their mother alive is hurting her. The people qualified to set that threshold are
Thomas, the medtech advisor, and someone with clinical eldercare experience — not
an agent at 1am who has just found the bug and wants to close it.

So this does the smaller honest thing: it makes the gap impossible to mistake for
a working guard.

`tests/test_boundary_guardian_is_wired.py` **fails, on purpose**, with four
assertions — no caller, message unread, orphan metadata keys, decorative
thresholds. It is red until the guard is real. A skip would have been a note; a
failure is a blocker.

**Note on that test.** Its first version PASSED two of the four, because the
grep matched the test file itself asserting the absence. A check whose input
contains the check cannot fail — the exact defect the file exists to catch,
committed inside it within a minute of writing it. `_NOT_A_CALLER` now excludes
it, and the comment records why.

## What wiring it would require

1. A producer for `abuse_detected` / `isolation_pattern`, or a rewrite of
   `assess()` to read `message` directly.
2. A decision about false-positive cost, made by people qualified to make it.
3. A threshold that reads its own config instead of the literal 0.9.
4. Escalation routing: `ALERT_AUTHORITIES` currently names no authority and no
   channel.
5. Tests that make it say **no** — the guard has never once returned anything
   but "continue", and a guard nobody has watched refuse is not known to refuse.
