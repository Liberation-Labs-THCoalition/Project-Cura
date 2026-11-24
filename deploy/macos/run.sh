#!/bin/bash
# Cura's two processes on a household Mac, for the LaunchDaemon that runs this file as the hidden user `cura`.
#
#   cura run                       the scheduled check-in calls
#   cura webhook --port $CURA_PORT the server Twilio reaches through the Mac's own tunnel (listens on 127.0.0.1)
#
# Exactly one copy of each runs. If either stops, it is started again after a pause that grows with each quick
# failure (5 s up to 5 min), so a broken install does not spin. Everything goes to $CURA_HOME/daemon.log.
# Written for macOS's /bin/bash 3.2: no `wait -n`, no associative arrays.
#
# Settings come from the daemon's environment (never from this file, which is public):
#   CURA_PORT        required: the port the tunnel sends to (18675 on the Mac this was written for; 5000 is AirPlay's)
#   CURA_ELDER_NAME  optional: how Cura addresses the person on inbound calls
#   CURA_BIN         optional: the cura command (default /Users/cura/cura/venv/bin/cura)
#   CURA_HOME        optional: the folder for the log (default /Users/cura/cura)
set -u

export HOME=/Users/cura
CURA_HOME="${CURA_HOME:-/Users/cura/cura}"
CURA_BIN="${CURA_BIN:-/Users/cura/cura/venv/bin/cura}"
LOG="$CURA_HOME/daemon.log"

NAP_PID=""
nap() { sleep "$1" & NAP_PID=$!; wait "$NAP_PID" 2>/dev/null; NAP_PID=""; }   # a sleep a TERM can interrupt
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') run.sh: $*" >> "$LOG"; }

if [ -z "${CURA_PORT:-}" ]; then
  log "CURA_PORT is empty; refusing to start (no fallback to 5000: on a Mac that is AirPlay's port)"
  exit 78
fi
case "$CURA_PORT" in
  *[!0-9]*) log "CURA_PORT is not a number: refusing to start"; exit 78 ;;
esac
if [ ! -x "$CURA_BIN" ]; then
  log "no cura command at $CURA_BIN; refusing to start"
  exit 78
fi

RUN_PID=""; HOOK_PID=""; RUN_PAUSE=5; HOOK_PAUSE=5; RUN_START=0; HOOK_START=0

start_run() {
  "$CURA_BIN" run >> "$LOG" 2>&1 &
  RUN_PID=$!; RUN_START=$(date +%s); log "started cura run (pid $RUN_PID)"
}
start_hook() {
  if [ -n "${CURA_ELDER_NAME:-}" ]; then
    "$CURA_BIN" webhook --port "$CURA_PORT" --elder-name "$CURA_ELDER_NAME" >> "$LOG" 2>&1 &
  else
    "$CURA_BIN" webhook --port "$CURA_PORT" >> "$LOG" 2>&1 &
  fi
  HOOK_PID=$!; HOOK_START=$(date +%s); log "started cura webhook on 127.0.0.1:$CURA_PORT (pid $HOOK_PID)"
}

# The next pause: doubled after a quick failure (under 60 s of life), reset after a long run, capped at 300 s.
next_pause() {
  local pause=$1 started=$2 lived
  lived=$(( $(date +%s) - started ))
  if [ "$lived" -lt 60 ]; then pause=$(( pause * 2 )); [ "$pause" -gt 300 ] && pause=300; else pause=5; fi
  echo "$pause"
}

stop_all() {
  log "stopping (signal)"
  [ -n "$RUN_PID" ] && kill "$RUN_PID" 2>/dev/null
  [ -n "$HOOK_PID" ] && kill "$HOOK_PID" 2>/dev/null
  [ -n "$NAP_PID" ] && kill "$NAP_PID" 2>/dev/null
  wait 2>/dev/null
  exit 0
}
trap stop_all TERM INT

start_run
start_hook
while true; do
  nap 5
  if ! kill -0 "$RUN_PID" 2>/dev/null; then
    wait "$RUN_PID" 2>/dev/null; rc=$?
    RUN_PAUSE=$(next_pause "$RUN_PAUSE" "$RUN_START")
    log "cura run stopped (exit $rc); starting again in ${RUN_PAUSE}s"
    nap "$RUN_PAUSE"; start_run
  fi
  if ! kill -0 "$HOOK_PID" 2>/dev/null; then
    wait "$HOOK_PID" 2>/dev/null; rc=$?
    HOOK_PAUSE=$(next_pause "$HOOK_PAUSE" "$HOOK_START")
    log "cura webhook stopped (exit $rc); starting again in ${HOOK_PAUSE}s"
    nap "$HOOK_PAUSE"; start_hook
  fi
done
