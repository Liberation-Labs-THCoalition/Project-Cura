#!/usr/bin/env python3
"""Agent Army fail-state replay runner.

Forked from multiverse-code-assistant/eval/run_eval.py. That harness scored
model answers on a similarity ratio and folded transport errors into a zero
score; this one replays *recorded defects* and refuses to do either.

What it is for
--------------
When an Agent Army specialist finds a defect, the finding is written to
`.agent-army/fail-states/FS-<12 hex>.json` as a replayable regression test.
This runner replays the corpus and reports one of exactly three verdicts per
case: PASS, FAIL, ERROR.

  PASS  — the recorded repro no longer reproduces. The defect appears fixed.
  FAIL  — the recorded repro still reproduces. The defect is still there.
  ERROR — the harness could not determine either. Never counted as health.

The ERROR bucket is the whole point. `pytest` exit 5 means "no tests
collected" — a deleted fixture. Folding that into PASS would manufacture
evidence of health, so exit codes outside {0, 1} are ERROR, always.

Canaries
--------
Three self-checks in `.agent-army/canaries/` run before any case:

  CANARY-red    must report FAIL  (a fixture that asserts its own failure)
  CANARY-err    must report ERROR (points at an artifact that is not there)
  CANARY-empty  must report ERROR (a pytest file that collects zero tests)

If any canary deviates from its expected verdict the runner prints
REPLAY HARNESS UNTRUSTWORTHY, prints no case results at all, and exits
nonzero. A run cannot come back all-green by construction: canary-red always
contributes a FAIL and the other two always contribute ERRORs.

Exit codes
----------
  0  --status only. A replay run never returns 0 (see canary floor).
  1  canary floor: canaries healthy, no corpus ERROR, no regression.
  2  REPLAY HARNESS UNTRUSTWORTHY — canary deviated, results withheld.
  3  a corpus case resolved to ERROR.
  4  regression: a case with status "fixed" resolved to FAIL.

A CI gate should treat exit 1 as clean and >= 2 as actionable.

Usage
-----
  python3 replay.py                     # replay the whole corpus
  python3 replay.py --status            # one-line ledger summary, no execution
  python3 replay.py --case FS-0123...   # replay one case
  python3 replay.py --dry-run           # do not write ledger updates
  python3 replay.py --json out.json     # machine-readable results
"""

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------

PASS, FAIL, ERROR = "PASS", "FAIL", "ERROR"
# SEED: a record transcribed from history, never observed failing. Reported
# and counted, never gating -- it is a claim awaiting proof, not a test.
SEED = "SEED"

EXIT_STATUS_OK = 0
EXIT_CANARY_FLOOR = 1
EXIT_UNTRUSTWORTHY = 2
EXIT_CORPUS_ERROR = 3
EXIT_REGRESSION = 4

DEFAULT_TIMEOUT = 120
DEFAULT_STALE_DAYS = 30
DEFAULT_MODEL_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# pytest's documented exit codes. Anything not in {0, 1} is ERROR.
PYTEST_EXIT_MEANING = {
    0: "all tests passed",
    1: "tests were collected and run, some failed",
    2: "run interrupted by user",
    3: "internal pytest error",
    4: "pytest usage error (e.g. file not found)",
    5: "NO TESTS COLLECTED - fixture missing or renamed",
}

REQUIRED_FIELDS = ("id", "class", "kind", "title", "repro", "status")
VALID_STATUS = ("open", "fixed", "rejected", "quarantined", "unverified")
NON_GATING_STATUS = ("rejected", "quarantined")


def now_iso():
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------
# result record
# --------------------------------------------------------------------------

class Result:
    __slots__ = ("case_id", "verdict", "reason", "detail", "path", "status",
                 "returncode", "promoted", "gating")

    def __init__(self, case_id, verdict, reason, detail="", path=None,
                 status=None, returncode=None, gating=True):
        self.case_id = case_id
        self.verdict = verdict
        self.reason = reason
        self.detail = detail
        self.path = path
        self.status = status
        self.returncode = returncode
        self.promoted = False
        self.gating = gating

    def as_dict(self):
        return {
            "id": self.case_id, "verdict": self.verdict, "reason": self.reason,
            "status": self.status, "returncode": self.returncode,
            "promoted": self.promoted, "gating": self.gating,
            "path": str(self.path) if self.path else None,
            "detail": self.detail[-4000:],
        }


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def load_case(path):
    """Return (case_dict, error_string). A malformed file is an ERROR case,
    never a silently skipped one."""
    try:
        raw = path.read_text()
    except OSError as e:
        return None, "unreadable: %s" % e
    try:
        case = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, "malformed JSON: %s" % e
    if not isinstance(case, dict):
        return None, "malformed: top level is %s, expected object" % type(case).__name__
    missing = [f for f in REQUIRED_FIELDS if f not in case]
    if missing:
        return case, "schema: missing required field(s): %s" % ", ".join(missing)
    if case.get("status") not in VALID_STATUS:
        return case, "schema: status %r not one of %s" % (case.get("status"), list(VALID_STATUS))
    repro = case.get("repro")
    if not isinstance(repro, dict) or "harness" not in repro:
        return case, "schema: repro must be an object with a harness field"
    if repro["harness"] != "none" and not repro.get("command"):
        return case, "schema: repro.command is empty for harness %r" % repro["harness"]
    return case, None


def load_dir(d):
    """Yield (path, case, error) for every *.json in d, sorted by name."""
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        case, err = load_case(p)
        out.append((p, case, err))
    return out


# --------------------------------------------------------------------------
# source artifact verification
# --------------------------------------------------------------------------

def git(repo, *args, timeout=30):
    try:
        cp = subprocess.run(["git", "-C", str(repo)] + list(args),
                            capture_output=True, text=True, timeout=timeout)
        return cp.returncode, cp.stdout, cp.stderr
    except FileNotFoundError:
        return 127, "", "git executable not found"
    except subprocess.TimeoutExpired:
        return 124, "", "git timed out"


def verify_source_artifact(repo, case):
    """A moved or deleted source artifact is an ERROR, not a silent pass.

    The spec's literal check is `git cat-file -e <git_rev>:<path>`. That check
    alone cannot detect a move or a delete: the recorded revision still
    contains the file forever. So we run three checks:

      1. the recorded revision is still reachable in this repo
      2. the artifact existed at that revision   (the literal spec check)
      3. the artifact still exists at HEAD       (catches move/delete)

    Returns (ok, reason).
    """
    art = case.get("source_artifact")
    if not art:
        return True, "no source_artifact recorded (skipped)"
    path = art.get("path")
    rev = art.get("git_rev")
    if not path or not rev:
        return False, "source_artifact incomplete: path=%r git_rev=%r" % (path, rev)

    rc, _, err = git(repo, "rev-parse", "--is-inside-work-tree")
    if rc != 0:
        return False, "not a git repo: %s (%s)" % (repo, err.strip())

    rc, _, err = git(repo, "cat-file", "-e", "%s^{commit}" % rev)
    if rc != 0:
        return False, "recorded git_rev %s no longer reachable in %s" % (rev, repo)

    rc, _, err = git(repo, "cat-file", "-e", "%s:%s" % (rev, path))
    if rc != 0:
        return False, "artifact absent at recorded rev: %s:%s" % (rev, path)

    rc, _, err = git(repo, "cat-file", "-e", "HEAD:%s" % path)
    if rc != 0:
        return False, "artifact moved or deleted since discovery: HEAD:%s missing" % path

    return True, "artifact present at %s and HEAD" % rev[:12]


# --------------------------------------------------------------------------
# the strict oracle
# --------------------------------------------------------------------------

def strict_oracle(output, must_contain, must_not_contain, case_sensitive=False):
    """No partial credit. Any must_not_contain hit is FAIL, full stop.

    The forked harness scored `round(hits / len(must_contain) * 3)`, so a
    response could miss two thirds of its required content and still book a
    passing accuracy score. This one is all-or-nothing.

    Returns (ok, reason).
    """
    hay = output if case_sensitive else output.lower()

    for pat in (must_not_contain or []):
        needle = pat if case_sensitive else pat.lower()
        if needle in hay:
            return False, "forbidden pattern present: %r" % pat

    missing = []
    for pat in (must_contain or []):
        needle = pat if case_sensitive else pat.lower()
        if needle not in hay:
            missing.append(pat)
    if missing:
        return False, "required pattern(s) absent: %s" % ", ".join(repr(m) for m in missing)

    return True, "oracle satisfied"


# --------------------------------------------------------------------------
# harness lanes
# --------------------------------------------------------------------------

def run_process(command, cwd, timeout, env=None):
    """Returns (returncode, combined_output, launch_error_or_None)."""
    if isinstance(command, list):
        argv, shell = command, False
    else:
        argv, shell = command, True
    try:
        cp = subprocess.run(
            argv, shell=shell, cwd=str(cwd), capture_output=True, text=True,
            timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired as e:
        partial = (e.stdout or "") + (e.stderr or "")
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        return None, partial, "timed out after %ss" % timeout
    except FileNotFoundError as e:
        return None, "", "could not launch: %s" % e
    except OSError as e:
        return None, "", "could not launch: %s" % e
    return cp.returncode, (cp.stdout or "") + (cp.stderr or ""), None


def lane_pytest(case, ctx):
    repro = case["repro"]
    rc, out, launch_err = run_process(repro["command"], ctx["cwd"], ctx["timeout"])

    if launch_err:
        return Result(case["id"], ERROR, "pytest could not run: %s" % launch_err, out)

    # Three buckets, and ERROR is never folded into PASS.
    if rc not in (0, 1):
        meaning = PYTEST_EXIT_MEANING.get(rc, "undocumented pytest exit code")
        return Result(case["id"], ERROR,
                      "pytest exit %d: %s" % (rc, meaning), out, returncode=rc)

    ok, why = strict_oracle(out, repro.get("must_contain"),
                            repro.get("must_not_contain"),
                            repro.get("case_sensitive", False))
    if not ok:
        return Result(case["id"], FAIL, "oracle: %s" % why, out, returncode=rc)

    if rc == 0:
        return Result(case["id"], PASS, "pytest exit 0, oracle satisfied", out, returncode=0)
    return Result(case["id"], FAIL, "pytest exit 1: repro still fails", out, returncode=1)


def lane_command(case, ctx):
    repro = case["repro"]
    rc, out, launch_err = run_process(repro["command"], ctx["cwd"], ctx["timeout"])

    if launch_err:
        return Result(case["id"], ERROR, "command could not run: %s" % launch_err, out)
    if rc in (126, 127):
        return Result(case["id"], ERROR,
                      "command not executable/not found (exit %d)" % rc, out, returncode=rc)
    if rc is not None and rc < 0:
        return Result(case["id"], ERROR,
                      "command killed by signal %d" % -rc, out, returncode=rc)

    ok, why = strict_oracle(out, repro.get("must_contain"),
                            repro.get("must_not_contain"),
                            repro.get("case_sensitive", False))
    if not ok:
        return Result(case["id"], FAIL, "oracle: %s" % why, out, returncode=rc)
    if rc == 0:
        return Result(case["id"], PASS, "command exit 0, oracle satisfied", out, returncode=0)
    return Result(case["id"], FAIL, "command exit %d" % rc, out, returncode=rc)


def lane_prompt(case, ctx):
    """agent-behavior lane: replay a prompt against a model endpoint.

    An unreachable endpoint is ERROR. It is never a pass and never a fail:
    if we could not ask the question we did not learn the answer.
    """
    repro = case["repro"]
    prompt = repro.get("prompt") or repro.get("command")
    model = repro.get("model") or ctx["model"]
    url = repro.get("model_url") or ctx["model_url"]
    if not url:
        return Result(case["id"], ERROR, "no model endpoint configured for agent-behavior replay")

    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"num_ctx": 32768}}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=ctx["timeout"]) as r:
            payload = json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
        return Result(case["id"], ERROR, "model endpoint unreachable (%s): %s" % (url, e))

    text = payload.get("response", "")
    ok, why = strict_oracle(text, repro.get("must_contain"),
                            repro.get("must_not_contain"),
                            repro.get("case_sensitive", False))
    if not ok:
        return Result(case["id"], FAIL, "oracle: %s" % why, text)
    return Result(case["id"], PASS, "oracle satisfied", text)


def lane_none(case, ctx):
    """Seed records: transcribed from history, never observed failing.

    A seeded record has no repro command by construction -- fabricating one
    would be inventing evidence. Without this lane such a case books ERROR on
    every run forever, which is the always-ERROR state the emit rules warn
    trains people to ignore the runner. SEED is reported, counted, and
    explicitly non-gating.
    """
    return Result(case["id"], SEED,
                  "seed record: transcribed from history, not replayable "
                  "(no observed red proof)")


LANES = {
    "none": lane_none,
    "pytest": lane_pytest,
    "command": lane_command,
    "shell": lane_command,
    "prompt": lane_prompt,
    "agent-behavior": lane_prompt,
}


# --------------------------------------------------------------------------
# replay
# --------------------------------------------------------------------------

def replay_case(path, case, load_err, ctx):
    cid = (case or {}).get("id") or path.stem
    status = (case or {}).get("status")
    gating = status not in NON_GATING_STATUS

    if load_err:
        return Result(cid, ERROR, load_err, path=path, status=status, gating=True)

    ok, why = verify_source_artifact(ctx["repo"], case)
    if not ok:
        return Result(cid, ERROR, "source artifact check failed: %s" % why,
                      path=path, status=status, gating=gating)

    harness = case["repro"]["harness"]
    lane = LANES.get(harness)
    if lane is None:
        return Result(cid, ERROR, "unknown harness %r (known: %s)"
                      % (harness, ", ".join(sorted(LANES))),
                      path=path, status=status, gating=gating)

    r = lane(case, ctx)
    r.path = path
    r.status = status
    r.gating = gating
    return r


# --------------------------------------------------------------------------
# ledger writeback + auto-promotion
# --------------------------------------------------------------------------

def write_case(path, case):
    tmp = tempfile.NamedTemporaryFile("w", dir=str(path.parent), delete=False,
                                      prefix=".%s." % path.name, suffix=".tmp")
    try:
        json.dump(case, tmp, indent=2)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, str(path))
    except BaseException:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def update_ledger(path, case, result, ctx):
    """Record the replay and auto-promote open -> fixed on first PASS."""
    if case is None:
        return
    stamp = now_iso()
    case["last_replayed"] = stamp
    case["replay_count"] = int(case.get("replay_count") or 0) + 1
    if result.verdict == FAIL:
        case["fail_count"] = int(case.get("fail_count") or 0) + 1
    if result.verdict == ERROR:
        case["error_count"] = int(case.get("error_count") or 0) + 1

    log = case.setdefault("log", [])
    if not isinstance(log, list):
        log = case["log"] = []

    rc, head, _ = git(ctx["repo"], "rev-parse", "HEAD")
    head = head.strip() if rc == 0 else None

    if result.verdict == PASS and case.get("status") == "open":
        case["status"] = "fixed"
        result.promoted = True
        log.append({
            "at": stamp, "event": "auto-promote", "from": "open", "to": "fixed",
            "verdict": PASS, "git_rev": head, "by": "replay.py",
            "note": "repro no longer reproduces: %s" % result.reason,
        })
    elif result.verdict == FAIL and case.get("status") == "fixed":
        log.append({
            "at": stamp, "event": "regression", "status": "fixed",
            "verdict": FAIL, "git_rev": head, "by": "replay.py",
            "note": result.reason,
        })
    elif result.verdict == ERROR:
        log.append({
            "at": stamp, "event": "replay-error", "status": case.get("status"),
            "verdict": ERROR, "git_rev": head, "by": "replay.py",
            "note": result.reason,
        })

    if not ctx["dry_run"]:
        write_case(path, case)


# --------------------------------------------------------------------------
# canary gate
# --------------------------------------------------------------------------

def run_canaries(root, ctx):
    """Returns (ok, canary_results, deviations)."""
    entries = load_dir(root / "canaries")
    results, deviations = [], []

    if not entries:
        deviations.append(("<none>", "expected 3 canaries, found 0 in %s"
                           % (root / "canaries")))
        return False, results, deviations

    for path, case, err in entries:
        expect = (case or {}).get("expect")
        r = replay_case(path, case, err, ctx)
        r.gating = False
        results.append((r, expect))
        if expect not in (PASS, FAIL, ERROR):
            deviations.append((r.case_id,
                               "canary declares no valid 'expect' field (got %r)" % expect))
        elif r.verdict != expect:
            deviations.append((r.case_id,
                               "expected %s, got %s -- %s" % (expect, r.verdict, r.reason)))

    seen = {r.case_id for r, _ in results}
    for required in ("CANARY-red", "CANARY-err", "CANARY-empty"):
        if required not in seen:
            deviations.append((required, "canary missing from %s" % (root / "canaries")))

    return (not deviations), results, deviations


# --------------------------------------------------------------------------
# --status
# --------------------------------------------------------------------------

def parse_iso(s):
    if not s:
        return None
    try:
        d = _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d


def cmd_status(root, stale_days):
    entries = load_dir(root / "fail-states")
    now = _dt.datetime.now(_dt.timezone.utc)
    counts = {s: 0 for s in VALID_STATUS}
    malformed = no_red_proof = stale = never = fresh = 0

    for _path, case, err in entries:
        if err or case is None:
            malformed += 1
            continue
        st = case.get("status")
        if st in counts:
            counts[st] += 1
        rp = case.get("red_proof")
        if not rp or not isinstance(rp, dict) or rp.get("exit_code") is None:
            no_red_proof += 1
        last = parse_iso(case.get("last_replayed"))
        if last is None:
            never += 1
            stale += 1          # never replayed is stale, and is printed as such
        elif (now - last).days > stale_days:
            stale += 1
        else:
            fresh += 1

    canaries = len(list((root / "canaries").glob("*.json"))) if (root / "canaries").is_dir() else 0

    print(
        "STATUS ledger=%s cases=%d open=%d fixed=%d rejected=%d quarantined=%d "
        "unverified=%d no_red_proof=%d malformed=%d stale=%d never_replayed=%d "
        "fresh=%d stale_threshold_days=%d canaries=%d as_of=%s"
        % (root / "fail-states", len(entries), counts["open"], counts["fixed"],
           counts["rejected"], counts["quarantined"], counts["unverified"],
           no_red_proof, malformed, stale, never, fresh, stale_days,
           canaries, now_iso())
    )
    return EXIT_STATUS_OK


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

BAR = "=" * 72


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Agent Army fail-state replay runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="exit: 0 --status | 1 canary floor | 2 UNTRUSTWORTHY | "
               "3 corpus ERROR | 4 regression",
    )
    here = Path(__file__).resolve().parent
    ap.add_argument("--root", default=str(here),
                    help="directory holding fail-states/ and canaries/")
    ap.add_argument("--repo", default=None,
                    help="git repo for source-artifact verification (default: parent of --root)")
    ap.add_argument("--case", action="append", default=None,
                    help="replay only this case id (repeatable)")
    ap.add_argument("--status", action="store_true", help="print one-line ledger summary and exit")
    ap.add_argument("--dry-run", action="store_true", help="do not write ledger updates")
    ap.add_argument("--json", dest="json_out", default=None, help="write full results as JSON")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    ap.add_argument("--model", default="rivet", help="model for agent-behavior lane")
    ap.add_argument("--model-url", default=DEFAULT_MODEL_URL)
    ap.add_argument("-v", "--verbose", action="store_true", help="dump output of non-PASS cases")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    repo = Path(args.repo).resolve() if args.repo else root.parent

    if args.status:
        return cmd_status(root, args.stale_days)

    ctx = {"repo": repo, "cwd": repo, "timeout": args.timeout,
           "dry_run": args.dry_run, "model": args.model, "model_url": args.model_url}

    print("Agent Army fail-state replay")
    print("  ledger : %s" % (root / "fail-states"))
    print("  repo   : %s" % repo)
    print()

    # ---- canary gate: runs before anything, results withheld on deviation ----
    ok, canary_results, deviations = run_canaries(root, ctx)
    if not ok:
        print(BAR)
        print("REPLAY HARNESS UNTRUSTWORTHY")
        print(BAR)
        for cid, why in deviations:
            print("  %-14s %s" % (cid, why))
        print()
        print("  Case results are withheld. A harness that cannot prove it still")
        print("  detects failure cannot be trusted to report health.")
        print("  %d fail-state case(s) were NOT replayed." % len(load_dir(root / "fail-states")))
        return EXIT_UNTRUSTWORTHY

    print("CANARIES (harness self-check)")
    for r, expect in canary_results:
        print("  [%-5s] %-14s expected %-5s  %s" % (r.verdict, r.case_id, expect, r.reason))
    print("  -> all %d canaries behaved as declared; harness trusted" % len(canary_results))
    print()

    # ---- corpus ----
    entries = load_dir(root / "fail-states")
    if args.case:
        wanted = set(args.case)
        entries = [e for e in entries
                   if ((e[1] or {}).get("id") or e[0].stem) in wanted]
        missing = wanted - {((e[1] or {}).get("id") or e[0].stem) for e in entries}
        for m in sorted(missing):
            print("  [ERROR] %-14s requested case not found in ledger" % m)
        if missing:
            print()

    results = []
    print("CASES (%d)" % len(entries))
    if not entries:
        print("  (ledger empty)")
    for path, case, err in entries:
        r = replay_case(path, case, err, ctx)
        update_ledger(path, case, r, ctx)
        results.append(r)
        mark = ""
        if r.promoted:
            mark = "  [auto-promoted open -> fixed]"
        elif not r.gating:
            mark = "  [%s: non-gating]" % r.status
        elif r.verdict == FAIL and r.status == "fixed":
            mark = "  [REGRESSION]"
        print("  [%-5s] %-14s %s%s" % (r.verdict, r.case_id, r.reason, mark))
        if args.verbose and r.verdict != PASS and r.detail:
            for line in r.detail.rstrip().splitlines()[-25:]:
                print("        | %s" % line)
    print()

    # ---- tally ----
    c_pass = sum(1 for r in results if r.verdict == PASS)
    c_fail = sum(1 for r in results if r.verdict == FAIL)
    c_err = sum(1 for r in results if r.verdict == ERROR)
    c_seed = sum(1 for r in results if r.verdict == SEED)
    regressions = [r for r in results if r.verdict == FAIL and r.status == "fixed"]
    promoted = [r for r in results if r.promoted]
    # r.gating was computed, threaded through three constructors, stored in
    # __slots__, serialized in as_dict -- and read only to print a label. This
    # comprehension named itself "gating" and then ignored it, so `quarantined`
    # and `rejected`, the two statuses whose entire purpose is to stop a case
    # gating CI, gated it anyway. A computed flag that decorates output and
    # never reaches the decision. Found 2026-08-31; see FS record for this file.
    gating_err = [r for r in results if r.verdict == ERROR and r.gating]

    can_pass = sum(1 for r, _ in canary_results if r.verdict == PASS)
    can_fail = sum(1 for r, _ in canary_results if r.verdict == FAIL)
    can_err = sum(1 for r, _ in canary_results if r.verdict == ERROR)

    print(BAR)
    print("SUMMARY")
    print("  corpus   PASS=%d FAIL=%d ERROR=%d SEED=%d  (of %d cases)"
          % (c_pass, c_fail, c_err, c_seed, len(results)))
    print("  canaries PASS=%d FAIL=%d ERROR=%d  (expected 0/1/2 -- the nonzero floor)"
          % (can_pass, can_fail, can_err))
    print("  promoted open->fixed: %d   regressions: %d"
          % (len(promoted), len(regressions)))
    if args.dry_run:
        print("  --dry-run: no ledger writes were made")

    if gating_err:
        code = EXIT_CORPUS_ERROR
        verdict_line = "CORPUS ERROR - %d case(s) could not be determined; not counted as health" % len(gating_err)
    elif regressions:
        code = EXIT_REGRESSION
        verdict_line = "REGRESSION - %d fixed case(s) reproduce again" % len(regressions)
    else:
        code = EXIT_CANARY_FLOOR
        verdict_line = ("CLEAN CORPUS (exit 1 = canary floor; this runner never exits 0 "
                        "on a replay run)")
    print("  %s" % verdict_line)
    print("  exit %d" % code)
    print(BAR)

    if args.json_out:
        payload = {
            "at": now_iso(), "repo": str(repo), "root": str(root),
            "exit_code": code, "harness_trusted": True,
            "canaries": [{"expect": e, **r.as_dict()} for r, e in canary_results],
            "cases": [r.as_dict() for r in results],
            "totals": {"pass": c_pass, "fail": c_fail, "error": c_err,
                       "promoted": len(promoted), "regressions": len(regressions)},
        }
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(payload, indent=2))
        print("results -> %s" % args.json_out)

    return code


if __name__ == "__main__":
    sys.exit(main())
