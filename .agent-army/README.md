# Fail-state ledger

Findings from Agent Army audits of Cura live here as replayable regression tests.

`replay.py` is copied from Project-Agent-Army. Canaries included: a run cannot come
back all-green by construction, and an empty ledger exits nonzero on purpose.

Cura-specific note: a defect in what Cura SAYS is a safety defect, not a cosmetic
one. The people on the other end of these calls have dementia. A mistimed
medication prompt is a dosing risk; a voice that sounds like a machine is a
product failure. Severity here is judged by what reaches the household.
