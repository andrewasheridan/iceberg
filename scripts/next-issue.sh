#!/usr/bin/env bash
# Print the number of the next backlog issue to work on, or nothing if none is left.
#
# Order:
#   1. Issues pinned to the front (FIRST below), in that order, while still open.
#   2. Then by priority (high, medium, low), bugs first, then by issue number.
#
# Only issues written by a trusted author (TRUSTED_AUTHORS below) are eligible.
# Anyone can open an issue on this public repo, and the issue loop turns issues
# into auto-merging PRs, so issues from anyone else are never picked.
#
# Skipped: epics, issues labeled "blocked" or "needs triage", decision issues
# (titles that start with "Decide" or "Evaluate"), and issues that already
# have an open PR (branch "<type>/<N>-..." or body "Closes #N").
#
# Requires gh and jq.
set -euo pipefail

FIRST='[93]'
TRUSTED_AUTHORS='["andrewasheridan"]'

issues=$(gh issue list --state open --limit 500 --json number,title,labels,author)
prs=$(gh pr list --state open --limit 200 --json headRefName,body)

jq -rn \
  --argjson issues "$issues" \
  --argjson prs "$prs" \
  --argjson first "$FIRST" \
  --argjson trusted "$TRUSTED_AUTHORS" '
  ([$prs[]
    | ((.headRefName | (capture("^[a-z]+/(?<n>[0-9]+)-")? | .n)),
       (.body // "" | scan("(?i)(?:closes|fixes|resolves) #([0-9]+)")[0]))
    | tonumber] | unique) as $taken
  | def has_label($l): any(.labels[]; .name == $l);
    def prio: if has_label("priority: high") then 0
              elif has_label("priority: medium") then 1
              elif has_label("priority: low") then 2
              else 3 end;
  [$issues[]
    | select(.author.login as $a | $trusted | index($a))
    | select(has_label("epic") | not)
    | select(has_label("blocked") | not)
    | select(has_label("needs triage") | not)
    | select(.title | test("^(Decide|Evaluate)\\b") | not)
    | select(.number as $n | $taken | index($n) | not)
    | . as $i
    | ($first | index($i.number)) as $pos
    | {number,
       key: [(if $pos == null then 1 else 0 end),
             ($pos // 0),
             prio,
             (if has_label("type: bug") then 0 else 1 end),
             .number]}]
  | sort_by(.key)
  | first // empty
  | .number
'
