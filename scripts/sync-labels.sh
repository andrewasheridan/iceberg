#!/usr/bin/env bash
# Create or update the repository labels, and delete the GitHub default labels that
# this scheme replaces. Run again after you change this file.
#
# Usage: scripts/sync-labels.sh
set -euo pipefail

label() { gh label create "$1" --color "$2" --description "$3" --force; }

label "type: feature"  "a2eeef" "A new feature or a change in behavior"
label "type: bug"      "d73a4a" "Something does not work as it should"
label "type: docs"     "0075ca" "Documentation only"
label "type: refactor" "c5def5" "Code change that is not a fix or a feature"
label "type: test"     "bfd4f2" "Add or correct tests"
label "type: perf"     "fbca04" "Performance improvement"
label "type: build"    "5319e7" "Build system or dependencies"
label "type: ci"       "1d76db" "Continuous integration"
label "type: chore"    "ededed" "Maintenance and tooling"

label "priority: high"   "b60205" "Do this first"
label "priority: medium" "d93f0b" "Do this soon"
label "priority: low"    "0e8a16" "Do this when there is time"

label "epic"             "3e4b9e" "Parent issue that groups atomic sub-issues"
label "needs triage"     "fef2c0" "Not yet reviewed: set type and priority"
label "blocked"          "000000" "Cannot continue until something else is done"
label "breaking change"  "b60205" "Changes behavior that users depend on"
label "automated"        "ededed" "Opened by a workflow"

# Dependabot adds these to its pull requests.
label "dependencies" "0366d6" "Pull requests that update a dependency file"
label "python:uv"    "2b67c6" "Pull requests that update python:uv code"

# The type: labels above replace these GitHub defaults. Deleting a label that is
# already gone is not an error.
for default in bug documentation duplicate enhancement "good first issue" \
  "help wanted" invalid question wontfix; do
  gh label delete "$default" --yes 2>/dev/null || true
done
