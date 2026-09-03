# Design drafts — NOT shipped, NOT imported

Working artifacts from the `cura-household-model` workflow (wf_bb5f7ac4-fc3),
kept for reference while the household model is decided.

**`household_model_draft3.py`** — design 3's model, 674 lines. It was written
directly into `cura/household.py` by a workflow agent and I committed it there
by accident with `git add -A`, in a commit about something else entirely. Moved
here so it stops looking like a shipped module.

Read it as a sketch, not a proposal. Its own judge found a **safety-critical**
flaw: `responders_for` never consults `Initiative`, so it would place an
escalation call to a person recorded as never-to-be-called — in the first
household, that is the woman who cannot answer a phone becoming the emergency
contact. All three designs had a version of that same flaw independently.

The decision page is `docs/HOUSEHOLD_MODEL_DECISION.md`.

**Process note:** after a workflow that can write to the repo, check
`git status` before `git add -A`. Agents leave artifacts, and a sweep commits
them under whatever message the real change had.
