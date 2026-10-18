"""The docs describe the wiring that exists (rollout spec C4, 2026-10-17). Cura never used Kintsugi; CLAUDE.md and the
pulse docstring said it did. Each assertion goes red if the old claim comes back."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = (ROOT / "CLAUDE.md").read_text()


def test_claude_md_claims_no_kintsugi_primitives():
    assert "Built on Kintsugi Engine primitives" not in CLAUDE
    assert not re.search(r"^- \*\*(Pulse|EFE|Shield Module|Comms Dispatcher)\*\* —", CLAUDE, re.M)
    assert "Kintsugi:** not used" in CLAUDE


def test_the_pulse_docstring_does_not_claim_the_kintsugi_pulse():
    head = (ROOT / "cura" / "pulse" / "eldercare_pulse.py").read_text()[:400]
    assert "Configures the Kintsugi Pulse" not in head


def test_the_expected_count_matches_the_collected_tests():
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "tests"],
                         cwd=ROOT, capture_output=True, text=True, timeout=300).stdout
    collected = int(re.search(r"(\d+) tests? collected", out).group(1))
    assert f"Expected: {collected} passed." in CLAUDE, f"CLAUDE.md's expected count is stale: {collected} collected"
    assert f"Test suite ({collected} tests)" in CLAUDE


def test_no_new_python_file_names_the_shelved_guard():
    # tests/test_boundary_guardian_is_wired.py greps the repo for this name; a mention in any other file would silently
    # disarm it. The two files that may name it are pinned (checked without git, so a copy without .git still checks).
    # The name is built from parts here so this file isn't a third.
    name = "Elder" + "Guardian"
    allowed = {"cura/tools/boundary_guardian.py", "tests/test_boundary_guardian_is_wired.py"}
    offenders = sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob("*.py")
                       if ".venv" not in p.parts and str(p.relative_to(ROOT)) not in allowed and name in p.read_text())
    assert not offenders, offenders
