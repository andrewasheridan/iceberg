#!/usr/bin/env bash
# PreToolUse hook: ask the user before a Bash command merges a pull request.
#
# A permissions "ask" rule in settings.json also applies to headless sessions
# (`claude -p`). There, nobody can answer, so the command fails and the issue loop
# cannot enable auto-merge. Claude Code sets CLAUDE_CODE_ENTRYPOINT to "sdk-cli"
# for `claude -p`, so this hook asks only when the entry point is not an SDK.
set -euo pipefail

case "${CLAUDE_CODE_ENTRYPOINT:-}" in
  sdk-*) exit 0 ;;
esac

command="$(jq -r '.tool_input.command // ""')"

if [[ "$command" =~ gh[[:space:]]+pr[[:space:]]+merge ]] || [[ "$command" =~ gh[[:space:]]+api[[:space:]].*merge ]]; then
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "ask",
      permissionDecisionReason: "This command merges a pull request. Approve each merge."
    }
  }'
fi
