"""FS-e56ad5c01538 — a non-North-American number cannot be entered at all.

a_phone() accepts only 10 digits, or 11 beginning with 1, and the phone question
is required with no skip. Any other number re-asks forever with a message that
insists on "a 10-digit phone number", and setup can never be completed. norm_phone
would also mangle it, prefixing +1 to a foreign number.
"""
import sys
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def run_cura(args, home, stdin_text="", timeout=60):
    """Run `python -m cura ...` against a throwaway HOME, as the caregiver would."""
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
    return subprocess.run([sys.executable, "-m", "cura", *args], cwd=str(ROOT),
                          input=stdin_text, capture_output=True, text=True,
                          env=env, timeout=timeout)


def written_config(home):
    d = pathlib.Path(home) / ".cura"
    files = [f for f in d.glob("*.json") if f.name != "setup-progress.json"]
    assert files, f"setup wrote no config into {d}"
    return json.loads(files[0].read_text())

sys.path.insert(0, str(ROOT))


def test_international_number_is_accepted():
    from cura.setup.wizard import a_phone
    problem = a_phone("+44 20 7946 0958")
    assert problem is None, (
        "setup refuses a valid international number and offers no way past the "
        "question: " + str(problem))
