#!/usr/bin/env bash
# Work the issue backlog in sequence, one new headless Claude Code session per issue.
#
# For each issue: pick it with scripts/next-issue.sh, run `claude -p "/next-issue N"`,
# wait for the PR checks, wait for the auto-merge, and continue on the updated main.
# Stops at the first blocked issue, failed check, or PR that does not merge.
# Stops (and turns auto-merge off) when a PR changes .github/workflows/.
#
# Sweeps: a sweep is one headless `claude -p "/sweep ..."` session that reviews the
# code and files new issues labeled "needs triage". It changes no code. A sweep runs
# after every SWEEP_EVERY merged issues, and once when the backlog is empty, before
# the loop exits. The loop skips "needs triage" issues until the maintainer removes
# the label. The SHA of the last sweep is saved in .issue-loop/last-sweep, and the
# next sweep reviews the commits after it in depth.
#
# Usage: scripts/issue-loop.sh [--once] [--max N] [--sweep | --no-sweep]
#
#   --once      work on one issue, then stop
#   --max N     work on at most N issues, then stop
#   --sweep     run only a sweep, then stop
#   --no-sweep  never run a sweep
#
# Environment:
#   CLAUDE_PERMISSION_MODE  permission mode for each session (default: auto)
#   CLAUDE_MAX_BUDGET_USD   optional spend limit for each session
#   MERGE_TIMEOUT_MIN       minutes to wait for a merge after checks pass (default: 30)
#   SWEEP_EVERY             merged issues between sweeps; 0 turns this off (default: 5)
#   SWEEP_MAX_ISSUES        most issues one sweep may file (default: 3)
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; }

max=0
sweeps=1
sweep_only=0
while [ $# -gt 0 ]; do
  case "$1" in
    --once) max=1 ;;
    --max) max="$2"; shift ;;
    --sweep) sweep_only=1 ;;
    --no-sweep) sweeps=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
if [ "$sweep_only" -eq 1 ] && [ "$sweeps" -eq 0 ]; then
  echo "--sweep and --no-sweep cannot be used together" >&2; exit 2
fi

mode="${CLAUDE_PERMISSION_MODE:-auto}"
merge_timeout=$(( ${MERGE_TIMEOUT_MIN:-30} * 60 ))
sweep_every="${SWEEP_EVERY:-5}"
sweep_max="${SWEEP_MAX_ISSUES:-3}"
log_dir=".issue-loop"
last_sweep_file="$log_dir/last-sweep"
mkdir -p "$log_dir"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\n!!! %s\n' "$*" >&2; exit 1; }

claude_args() {
  args=(-p "$1" --permission-mode "$mode")
  if [ -n "${CLAUDE_MAX_BUDGET_USD:-}" ]; then args+=(--max-budget-usd "$CLAUDE_MAX_BUDGET_USD"); fi
}

sync_main() {
  [ -z "$(git status --porcelain)" ] || die "working tree is dirty; commit or stash first"
  git switch -q main
  git pull -q --ff-only
  git fetch -q --prune
}

run_sweep() {
  sync_main
  local head since log last
  head=$(git rev-parse HEAD)
  since=$(cat "$last_sweep_file" 2>/dev/null || true)
  log="$log_dir/$(date +%Y%m%d-%H%M%S)-sweep.log"
  say "sweep of ${since:-the last 20 commits}${since:+..$head}  (log: $log)"

  claude_args "/sweep $sweep_max${since:+ $since}"
  claude "${args[@]}" | tee "$log" || die "claude exited with an error during the sweep (see $log)"

  last=$(grep -E '^(SWEEP|BLOCKED): ' "$log" | tail -1 || true)
  case "$last" in
    "SWEEP: "*) ;;
    "BLOCKED: "*) die "sweep blocked: ${last#BLOCKED: }" ;;
    *) die "sweep: no SWEEP or BLOCKED line in the output (see $log)" ;;
  esac
  [ -z "$(git status --porcelain)" ] || die "the sweep left changes in the working tree (see $log)"

  echo "$head" > "$last_sweep_file"
  say "sweep done: ${last#SWEEP: }"
}

if [ "$sweep_only" -eq 1 ]; then
  run_sweep
  exit 0
fi

done_count=0
since_sweep=0  # issues merged since the last sweep in this run
swept=0        # a sweep has run in this run
while [ "$max" -eq 0 ] || [ "$done_count" -lt "$max" ]; do
  sync_main

  issue=$(scripts/next-issue.sh)
  if [ -z "$issue" ]; then
    say "no eligible issues left"
    # Sweep once before exiting, unless a sweep just ran with nothing merged after it.
    if [ "$sweeps" -eq 1 ] && { [ "$swept" -eq 0 ] || [ "$since_sweep" -gt 0 ]; }; then
      run_sweep
    fi
    exit 0
  fi

  title=$(gh issue view "$issue" --json title -q .title)
  log="$log_dir/$(date +%Y%m%d-%H%M%S)-$issue.log"
  say "#$issue $title  (log: $log)"

  claude_args "/next-issue $issue"
  claude "${args[@]}" | tee "$log" || die "claude exited with an error for #$issue (see $log)"

  last=$(grep -E '^(PR|BLOCKED): ' "$log" | tail -1 || true)
  case "$last" in
    "PR: "*) pr="${last#PR: }" ;;
    "BLOCKED: "*) die "#$issue blocked: ${last#BLOCKED: }" ;;
    *) die "#$issue: no PR or BLOCKED line in the output (see $log)" ;;
  esac

  # A PR that changes CI workflows must not merge without a person reviewing it.
  if gh pr diff "$pr" --name-only | grep -q '^\.github/workflows/'; then
    gh pr merge "$pr" --disable-auto || true
    die "$pr changes .github/workflows/; auto-merge turned off, review it by hand"
  fi

  say "waiting for checks on $pr"
  sleep 20  # give GitHub time to register the checks
  gh pr checks "$pr" --watch --fail-fast --interval 30 || die "checks failed on $pr"

  say "waiting for $pr to merge"
  waited=0
  while :; do
    state=$(gh pr view "$pr" --json state -q .state)
    [ "$state" = MERGED ] && break
    [ "$state" = CLOSED ] && die "$pr was closed without a merge"
    [ "$waited" -ge "$merge_timeout" ] && die "$pr did not merge within ${MERGE_TIMEOUT_MIN:-30} min"
    sleep 30; waited=$(( waited + 30 ))
  done

  [ "$(gh issue view "$issue" --json state -q .state)" = CLOSED ] \
    || die "$pr merged but #$issue is still open"

  say "#$issue done ($pr merged)"
  done_count=$(( done_count + 1 ))
  since_sweep=$(( since_sweep + 1 ))

  if [ "$sweeps" -eq 1 ] && [ "$sweep_every" -gt 0 ] && [ "$since_sweep" -ge "$sweep_every" ]; then
    run_sweep
    since_sweep=0
    swept=1
  fi
done
