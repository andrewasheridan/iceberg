#!/usr/bin/env bash
# Work the issue backlog in sequence, one new headless Claude Code session per issue.
#
# For each issue: pick it with scripts/next-issue.sh, run `claude -p "/next-issue N"`,
# wait for the PR checks, wait for the auto-merge, and continue on the updated main.
# Stops at the first blocked issue, failed check, or PR that does not merge.
#
# Usage: scripts/issue-loop.sh [--once] [--max N]
#
# Environment:
#   CLAUDE_PERMISSION_MODE  permission mode for each session (default: auto)
#   CLAUDE_MAX_BUDGET_USD   optional spend limit for each session
#   MERGE_TIMEOUT_MIN       minutes to wait for a merge after checks pass (default: 30)
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

max=0
while [ $# -gt 0 ]; do
  case "$1" in
    --once) max=1 ;;
    --max) max="$2"; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

mode="${CLAUDE_PERMISSION_MODE:-auto}"
merge_timeout=$(( ${MERGE_TIMEOUT_MIN:-30} * 60 ))
log_dir=".issue-loop"
mkdir -p "$log_dir"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\n!!! %s\n' "$*" >&2; exit 1; }

done_count=0
while [ "$max" -eq 0 ] || [ "$done_count" -lt "$max" ]; do
  [ -z "$(git status --porcelain)" ] || die "working tree is dirty; commit or stash first"
  git switch -q main
  git pull -q --ff-only
  git fetch -q --prune

  issue=$(scripts/next-issue.sh)
  [ -n "$issue" ] || { say "no eligible issues left"; exit 0; }

  title=$(gh issue view "$issue" --json title -q .title)
  log="$log_dir/$(date +%Y%m%d-%H%M%S)-$issue.log"
  say "#$issue $title  (log: $log)"

  args=(-p "/next-issue $issue" --permission-mode "$mode")
  if [ -n "${CLAUDE_MAX_BUDGET_USD:-}" ]; then args+=(--max-budget-usd "$CLAUDE_MAX_BUDGET_USD"); fi
  claude "${args[@]}" | tee "$log" || die "claude exited with an error for #$issue (see $log)"

  last=$(grep -E '^(PR|BLOCKED): ' "$log" | tail -1 || true)
  case "$last" in
    "PR: "*) pr="${last#PR: }" ;;
    "BLOCKED: "*) die "#$issue blocked: ${last#BLOCKED: }" ;;
    *) die "#$issue: no PR or BLOCKED line in the output (see $log)" ;;
  esac

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
done
