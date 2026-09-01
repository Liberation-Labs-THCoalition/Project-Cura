#!/usr/bin/env bash
# FS-625a88c14716 — install.sh has no `cd` to its own directory.
#
# Run from anywhere but the repository root it creates a stray .venv in the
# caller's directory, then fails on `-r requirements-core.txt`, leaks pip's raw
# "ERROR: Could not open requirements file" to the screen, and tells the user
# the problem is their internet connection. Re-running from the same place
# repeats it forever; there is no wording anywhere that points at the real cause.
#
# RED = exit 1 with the wrong diagnosis, from an invocation the user has no
# reason to know is wrong.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK" || exit 2

OUT="$(bash "$REPO/install.sh" </dev/null 2>&1)"; rc=$?

fail() { printf 'FS-625a88c14716 FAIL: %s\n' "$1"; printf '%s\n' "$OUT"; exit 1; }

[ "$rc" -eq 0 ] || {
  case "$OUT" in
    *"Could not open requirements file"*)
      fail "pip's raw error reached the caregiver; install.sh promises plain words only" ;;
  esac
  case "$OUT" in
    *"almost always the internet connection"*)
      fail "a missing requirements-core.txt was reported as an internet problem" ;;
  esac
  fail "install.sh failed (rc=$rc) when run from a directory other than the repo"
}
[ -d "$WORK/.venv" ] && fail "left a stray .venv in the caller's directory"
echo "FS-625a88c14716 PASS"
