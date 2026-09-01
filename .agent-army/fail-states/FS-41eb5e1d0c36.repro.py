"""FS-41eb5e1d0c36 — the credential temp file is created world-readable, and the
chmod that is supposed to fix it happens too late and is allowed to fail silently.

add_phone.py, lines 124-131:

    tmp = cfg_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2))   # <- 0644, holds the auth token
    os.replace(tmp, cfg_path)                   # <- carries 0644 onto the config
    try:
        cfg_path.chmod(0o600)                   # the auth token lives here now
    except OSError:
        pass                                    # <- and if this fails, nothing says so

Three separate problems in eight lines:

  1. The temp file is created at the umask default. Observed: 0664 here, 0644
     under a normal umask. It contains the full Twilio auth token.
  2. os.replace preserves the source inode's mode, so the config itself is
     0644 between the replace and the chmod. Any reader in that window gets the
     token, and the file is left at 0644 for good if the process dies there.
  3. The chmod's failure is swallowed. On a filesystem that does not carry
     POSIX modes -- an exFAT stick, a network home, a Windows-hosted share, all
     plausible for a rural user with an external drive -- chmod raises and the
     token stays world-readable while the caregiver is told "Phone calls are on."

The fix is one line: create the temp file with mode 0600 before writing
(os.open with O_CREAT|O_EXCL and 0o600, or write then chmod the *temp*), and
surface a chmod failure instead of passing.

RED = at any point in the write sequence, a file containing the auth token is
readable by group or other.
"""
import json
import os
import pathlib
import tempfile

TOKEN = "abcdef0123456789abcdef0123456789"

ADD_PHONE = (pathlib.Path(__file__).resolve().parents[2]
             / "cura" / "setup" / "add_phone.py")


def test_temp_file_holding_the_token_is_never_world_readable():
    """Replay add_phone.py's exact write sequence and watch the temp file."""
    with tempfile.TemporaryDirectory() as td:
        cfg_path = pathlib.Path(td) / "margaret.json"
        cfg_path.write_text(json.dumps({"name": "Margaret Chen"}))
        os.chmod(cfg_path, 0o600)

        cfg = json.loads(cfg_path.read_text())
        cfg["twilio"] = {"account_sid": "AC" + "1" * 32,
                         "auth_token": TOKEN,
                         "phone_number": "+13075550142"}

        tmp = cfg_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=2))
        tmp_mode = tmp.stat().st_mode & 0o777
        os.replace(tmp, cfg_path)
        after_replace = cfg_path.stat().st_mode & 0o777

        assert not (tmp_mode & 0o077), (
            f"the temp file carrying the Twilio auth token is created {oct(tmp_mode)}; "
            "add_phone.py writes it with Path.write_text and only chmods the "
            "final config, after os.replace has already copied this mode onto it."
        )
        assert not (after_replace & 0o077), (
            f"after os.replace the config is {oct(after_replace)} and holds the "
            "auth token; the chmod(0o600) that fixes it runs afterwards."
        )


def test_a_failed_chmod_is_not_swallowed():
    """A chmod that cannot be applied must not be reported as success."""
    src = ADD_PHONE.read_text()
    assert "except OSError:\n        pass" not in src, (
        "add_phone.py swallows a failed chmod(0o600) on the credential file. "
        "On a filesystem without POSIX modes the token stays world-readable "
        "and the caregiver is told 'Phone calls are on.'"
    )
