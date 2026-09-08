"""The elder-abuse guard is SHELVED. This file enforces one invariant:

    EITHER IT WORKS, OR IT DOES NOT CLAIM TO.

Shelved 2026-09-08 by Thomas — not a priority for this deployment, revisit only
with a qualified clinical partner. Classifying a struggling caregiver as abusive
is not something to wing, "either for my family or for strangers."

The previous version of this file failed on purpose, because the module's
docstring described active elder-abuse protection while the code could only ever
return {"action": "continue"}. That gap is now closed from the honest side: the
docstring says SHELVED. So these tests pass — and they go red the moment anyone
restores protective language without also wiring the thing up.

WHY THAT DIRECTION. A shelved feature is fine. A shelved feature that still reads
as shipped is the original defect in a nicer coat, and it is how a README ends up
promising a family something the code cannot do.

What was actually wrong, kept here because it is the reason the invariant exists:
  - zero production callers; nothing imported it
  - assess(self, message, metadata) NEVER read `message`
  - abuse_detected / isolation_pattern / abuse_severity: zero producers repo-wide

Delete this file only when the guard is wired AND reads the message. Not before.
"""
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parent.parent
GUARD = REPO / "cura/tools/boundary_guardian.py"

#: This file does not count as a caller. It was not excluded on the first
#: attempt, and two tests passed because the grep matched the very file
#: asserting the absence. A check whose input contains the check cannot fail.
_NOT_A_CALLER = ("boundary_guardian.py", "test_boundary_guardian_is_wired.py")

#: Words that assert active protection. Present in the docstring => must be wired.
_PROTECTIVE_CLAIMS = ("watches for", "protects vulnerable", "detection and protection")


def _grep(pattern: str) -> list[str]:
    r = subprocess.run(["grep", "-rn", "--include=*.py", pattern, str(REPO)],
                       capture_output=True, text=True)
    return [l for l in r.stdout.splitlines()
            if not any(skip in l for skip in _NOT_A_CALLER)]


def _is_wired() -> bool:
    return bool(_grep("ElderGuardian"))


def test_it_does_not_claim_protection_it_cannot_deliver():
    """THE INVARIANT. Restoring protective language without wiring turns this red."""
    doc = GUARD.read_text()[:2000].lower()
    claims = [c for c in _PROTECTIVE_CLAIMS if c in doc]
    if claims and not _is_wired():
        raise AssertionError(
            f"boundary_guardian.py claims active protection {claims} while having "
            f"no production caller. Either wire it into the message path, or say "
            f"SHELVED. It cannot describe itself as watching for abuse while being "
            f"unable to return anything but 'continue'.")


def test_the_shelved_status_is_stated_where_someone_will_see_it():
    """A shelved module that does not say so is indistinguishable from a live one."""
    head = GUARD.read_text()[:400].upper()
    assert "SHELVED" in head or _is_wired(), (
        "The guard is neither wired nor marked SHELVED in its first lines. "
        "Someone reading this module has no way to know it never runs.")


def test_assess_still_does_not_read_the_message_and_that_is_recorded():
    """Documents the defect so un-shelving cannot start from a false premise.
    If someone rewrites assess() to read the message, this test tells them to
    delete it — the file's whole reason is gone at that point."""
    src = GUARD.read_text()
    body = src[src.index("def assess("):src.index("def process(")]
    reads_message = "message" in body[body.index(")"):]
    if reads_message:
        raise AssertionError(
            "assess() now reads `message` — the guard may be real. Verify it is "
            "wired and tested, then DELETE this file; its premise no longer holds.")


def test_the_scam_half_is_genuinely_wired_and_stays_that_way():
    """The half that DOES work. Regression guard: scam defense is real, tested,
    and must not get shelved by association with the abuse half."""
    assert _grep("ScamShield"), "ScamShield lost its production caller"
    assert (REPO / "tests/test_scam_shield.py").exists(), "scam shield tests vanished"
