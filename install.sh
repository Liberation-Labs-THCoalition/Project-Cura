#!/usr/bin/env bash
# Cura installer.
#
# Written for someone setting Cura up for a parent, who is often also caring for
# that parent. They get short, unpredictable windows. So:
#   - safe to run again after an interruption; it picks up, never restarts
#   - installs only what Cura actually needs, so nothing compiles for minutes
#   - explains any failure in plain words, with the one thing to do next
#   - never prints a stack trace
set -u

BIG() { printf '\n  %s\n\n' "$*"; }
SAY() { printf '  %s\n' "$*"; }

BIG "Installing Cura"

# ---- Python -------------------------------------------------------------
PY=""
for c in python3.12 python3.11 python3 python; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  fi
done

if [ -z "$PY" ]; then
  SAY "Cura needs Python, version 3.10 or newer, and I can't find it."
  SAY ""
  SAY "You can get it here:"
  SAY "    https://www.python.org/downloads/"
  SAY ""
  SAY "Install that, then run this again. Nothing you've done is lost."
  exit 1
fi
SAY "Found Python: $("$PY" --version 2>&1)"

# ---- virtual environment (re-runnable) ----------------------------------
VENV=".venv"
if [ ! -d "$VENV" ]; then
  if ! "$PY" -m venv "$VENV" 2>/dev/null; then
    SAY ""
    SAY "Couldn't create Cura's private folder for its parts."
    SAY "On Debian or Ubuntu this usually means one package is missing:"
    SAY "    sudo apt install python3-venv python3-tk"
    SAY ""
    SAY "Install that, then run this again."
    exit 1
  fi
  SAY "Created Cura's private space for its parts."
else
  SAY "Cura's space already exists — reusing it."
fi

PIP="$VENV/bin/pip"
[ -x "$PIP" ] || PIP="$VENV/Scripts/pip.exe"   # Windows layout

SAY "Getting the pieces Cura needs. This takes a minute."
if ! "$PIP" install --quiet --upgrade pip >/dev/null 2>&1; then :; fi
if ! "$PIP" install --quiet -r requirements-core.txt; then
  SAY ""
  SAY "Couldn't download Cura's parts. This is almost always the internet"
  SAY "connection rather than anything you did."
  SAY ""
  SAY "Check you're online and run this again — it will carry on from here."
  exit 1
fi
SAY "All the pieces are in place."

# ---- the setup window needs Tk (Debian/Ubuntu ship Python without it) ----
if ! "$VENV/bin/python" -c 'import tkinter' 2>/dev/null \
   && ! "$VENV/Scripts/python.exe" -c 'import tkinter' 2>/dev/null; then
  SAY ""
  SAY "One more piece: the part of Python that draws windows is missing,"
  SAY "so Cura's setup window can't open yet. On Debian or Ubuntu:"
  SAY "    sudo apt install python3-tk"
  SAY ""
  SAY "You can still finish setup right here in this window — carrying on."
fi

# ---- hand off to the wizard ---------------------------------------------
PYBIN="$VENV/bin/python"
[ -x "$PYBIN" ] || PYBIN="$VENV/Scripts/python.exe"

BIG "Now let's set Cura up for the person it will be calling."
exec "$PYBIN" -m cura setup
