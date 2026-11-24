#!/bin/bash
# Cura's two processes on a household Mac, for the LaunchDaemon that runs this file as the hidden user `cura`.
#
#   cura run                                           the scheduled check-in calls
#   cura webhook --host 127.0.0.1 --port $CURA_PORT    the server Twilio reaches through the Mac's own tunnel
#
# Exactly one copy of each runs. If either stops, it is started again after a pause that doubles after each quick
# failure (5 s up to 5 min), so a broken install does not spin. The two are watched independently: one waiting out
# its pause never delays noticing the other. Everything goes to $CURA_HOME/daemon.log.
# Written for macOS's /bin/bash 3.2: no `wait -n`, no associative arrays.
#
# Settings:
#   CURA_PORT        required, from the daemon's environment (set by the installer, root-owned): the port the
#                    tunnel sends to (18675 on the Mac this was written for; 5000 is AirPlay's).
#   CURA_BIN         optional: the cura command (default /Users/cura/cura/venv/bin/cura)
#   CURA_HOME        optional: the folder for the log (default /Users/cura/cura)
# Optional file /Users/cura/.cura/daemon.env (never in this public repo), for what the support account must be able
# to change without root: KEY=VALUE lines, read (never sourced), only if `cura` owns it and nobody else can write it.
# Only these keys are taken from it:
#   CURA_ELDER_NAME  how Cura addresses the person on inbound calls (default: the preferred name `cura setup` saved)
#   CURA_CONFIG      the config to use (default: the one `cura setup` wrote)
# Both commands find what `cura setup` wrote in ~/.cura on their own, so the file is needed only to override that.
set -u

export HOME=/Users/cura
CURA_HOME="${CURA_HOME:-/Users/cura/cura}"
CURA_BIN="${CURA_BIN:-/Users/cura/cura/venv/bin/cura}"
LOG="$CURA_HOME/daemon.log"
ENV_FILE="${CURA_ENV_FILE:-$HOME/.cura/daemon.env}"

NAP_PID=""
nap() { sleep "$1" & NAP_PID=$!; wait "$NAP_PID" 2>/dev/null; NAP_PID=""; }   # a sleep a TERM can interrupt
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') run.sh: $*" >> "$LOG"; }

CURA_ELDER_NAME="${CURA_ELDER_NAME:-}"
CURA_CONFIG="${CURA_CONFIG:-}"
if [ -f "$ENV_FILE" ]; then
  perms=$(ls -ld "$ENV_FILE" | cut -c1-10)
  if [ ! -O "$ENV_FILE" ] || [ "$(echo "$perms" | cut -c6)" = "w" ] || [ "$(echo "$perms" | cut -c9)" = "w" ]; then
    log "ignoring $ENV_FILE: it must belong to $(id -un) and be writable by no one else ($perms)"
  else
    while IFS= read -r line || [ -n "$line" ]; do
      case "$line" in
        ''|'#'*) ;;
        CURA_ELDER_NAME=*) CURA_ELDER_NAME="${line#CURA_ELDER_NAME=}" ;;
        CURA_CONFIG=*) CURA_CONFIG="${line#CURA_CONFIG=}" ;;
        *) log "ignoring a line in $ENV_FILE: only CURA_ELDER_NAME and CURA_CONFIG are read" ;;
      esac
    done < "$ENV_FILE"
  fi
fi

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

RUN_PID=""; HOOK_PID=""
RUN_PAUSE=5; HOOK_PAUSE=5          # the next pause for each, doubled after a quick failure
RUN_START=0; HOOK_START=0          # when each was last started
RUN_DUE=0; HOOK_DUE=0              # when a stopped one may start again (0 = running)

start_run() {
  if [ -n "$CURA_CONFIG" ]; then "$CURA_BIN" run --config "$CURA_CONFIG" >> "$LOG" 2>&1 &
  else "$CURA_BIN" run >> "$LOG" 2>&1 &
  fi
  RUN_PID=$!; RUN_START=$(date +%s); RUN_DUE=0; log "started cura run (pid $RUN_PID)"
}
start_hook() {
  set -- webhook --host 127.0.0.1 --port "$CURA_PORT"
  [ -n "$CURA_ELDER_NAME" ] && set -- "$@" --elder-name "$CURA_ELDER_NAME"
  [ -n "$CURA_CONFIG" ] && set -- "$@" --config "$CURA_CONFIG"
  "$CURA_BIN" "$@" >> "$LOG" 2>&1 &
  HOOK_PID=$!; HOOK_START=$(date +%s); HOOK_DUE=0; log "started cura webhook on 127.0.0.1:$CURA_PORT (pid $HOOK_PID)"
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
  now=$(date +%s)
  if [ "$RUN_DUE" -eq 0 ] && ! kill -0 "$RUN_PID" 2>/dev/null; then
    wait "$RUN_PID" 2>/dev/null; rc=$?
    RUN_PAUSE=$(next_pause "$RUN_PAUSE" "$RUN_START"); RUN_DUE=$(( now + RUN_PAUSE )); RUN_PID=""
    log "cura run stopped (exit $rc); starting again in ${RUN_PAUSE}s"
  fi
  if [ "$HOOK_DUE" -eq 0 ] && ! kill -0 "$HOOK_PID" 2>/dev/null; then
    wait "$HOOK_PID" 2>/dev/null; rc=$?
    HOOK_PAUSE=$(next_pause "$HOOK_PAUSE" "$HOOK_START"); HOOK_DUE=$(( now + HOOK_PAUSE )); HOOK_PID=""
    log "cura webhook stopped (exit $rc); starting again in ${HOOK_PAUSE}s"
  fi
  if [ "$RUN_DUE" -ne 0 ] && [ "$now" -ge "$RUN_DUE" ]; then start_run; fi
  if [ "$HOOK_DUE" -ne 0 ] && [ "$now" -ge "$HOOK_DUE" ]; then start_hook; fi
done
