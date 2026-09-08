"""The elder-abuse guard is NOT WIRED. This test is red on purpose.

Found 2026-09-08 by a cardinality sweep. ElderGuardian.process() can return
exactly one value in the shipped system -- {"action": "continue"} -- and it is
dead twice over:

  1. ZERO production callers. No module imports it. No test exercised it.
  2. Even if wired it could not fire. assess(self, message, metadata) NEVER
     READS `message` -- the elder's own words are the first parameter and the
     body never touches them. Every branch reads metadata keys, and of those:
         scam_detected      2 producers, both returning it to an MCP client,
                            neither routing it to any guardian
         abuse_detected     0 producers anywhere in the repo
         isolation_pattern  0 producers
         abuse_severity     0 producers
         scam_severity      0 producers

The scam-defense half of Cura IS real -- ScamShield is wired into
checkin_composer.py and has tests. The CAREGIVER ABUSE, COERCION and ISOLATION
half has never been able to fire once.

The household this is built for, from the project's own handoff: a man in his
seventies in rural Wyoming, sole caregiver for his wife with late-stage
dementia. Caregiver-abuse detection matters most exactly where the caregiver is
alone and under strain.

WHY THIS TEST FAILS INSTEAD OF BEING SKIPPED
A skip is a note. This is a safety guard that the README describes as
protective, so the gap must be LOUD until it closes. Building the actual
detector needs Thomas and the medtech advisor -- text-classifying a struggling
caregiver as abusive has a false-positive cost measured in families -- so this
does not attempt it. It only refuses to let the gap be quiet.

Delete this file when the guard is wired AND reads the message. Not before.
"""
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parent.parent
GUARD = REPO / "cura/tools/boundary_guardian.py"


#: Files whose mentions do not count as a caller. THIS FILE IS IN THE LIST,
#: and it was not on the first attempt: two of these tests passed because the
#: grep matched the very test file asserting the absence. A check whose input
#: contains the check cannot fail. That is the exact defect this file exists to
#: catch, committed inside it, within a minute of writing it.
_NOT_A_CALLER = ("boundary_guardian.py", "test_boundary_guardian_is_wired.py")


def _grep(pattern: str) -> list[str]:
    r = subprocess.run(["grep", "-rn", "--include=*.py", pattern, str(REPO)],
                       capture_output=True, text=True)
    return [l for l in r.stdout.splitlines()
            if not any(skip in l for skip in _NOT_A_CALLER)]


def test_elder_guardian_has_a_production_caller():
    callers = _grep("ElderGuardian")
    assert callers, (
        "ElderGuardian has NO production caller. The elder-abuse, coercion and "
        "isolation guard is imported by nothing, so it has never run. "
        "Wire it into the message path (cura/comms/responder.py or "
        "cura/pulse/checkin_composer.py) or delete it -- a protective module "
        "that cannot run is worse than an absent one, because the README counts it.")


def test_assess_reads_the_elders_words():
    """The guard takes the elder's message and never looks at it."""
    src = GUARD.read_text()
    body = src[src.index("def assess("):src.index("def process(")]
    signature_end = body.index(")")
    uses = body[signature_end:].count("message")
    assert uses > 0, (
        "assess(self, message, metadata) never reads `message`. Every branch "
        "reads metadata keys instead, so the elder's own words cannot trigger "
        "the guard under any circumstance.")


def test_the_metadata_keys_the_guard_reads_are_produced_by_something():
    """A guard whose inputs nothing writes is a guard that cannot fire."""
    orphans = {k: _grep(f'"{k}"') for k in
               ("abuse_detected", "isolation_pattern", "abuse_severity")}
    dead = {k: v for k, v in orphans.items() if not v}
    assert not dead, (
        f"These metadata keys gate the abuse/isolation branches and NOTHING in "
        f"the repo ever sets them: {sorted(dead)}. The branches are unreachable, "
        f"so process() returns the constant 'continue' for every input.")


def test_configurable_alert_thresholds_are_actually_read():
    """alert_family_threshold / alert_authorities_threshold are config knobs no
    code reads -- escalation is decided by a hardcoded 0.9. A deployer lowering
    the bar for a fragile household changes nothing, silently."""
    src = GUARD.read_text()
    for knob in ("alert_family_threshold", "alert_authorities_threshold"):
        uses = src.count(knob)
        assert uses > 1, (
            f"{knob} is declared and never read (appears {uses}x, declaration "
            f"only). Severity routing uses a literal 0.9 at the comparison site, "
            f"so tuning this knob has no effect.")
