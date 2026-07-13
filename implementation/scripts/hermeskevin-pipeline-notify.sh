#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--dry-run" ]]; then
  dry_run=true
else
  dry_run=false
fi

readonly PROFILE=/home/ubuntu/.hermes/profiles/hermeskevin
session_key=$(sqlite3 "$PROFILE/state.db" "SELECT session_key FROM gateway_routing WHERE session_key LIKE 'agent:main:feishu:%' ORDER BY updated_at DESC LIMIT 1;")
chat_id=$(printf '%s' "$session_key" | awk -F: 'NF >= 5 { print $5 }')
[[ -n "$chat_id" ]] || { echo "No hermeskevin Feishu target is available" >&2; exit 1; }

if "$dry_run"; then
  printf 'target=feishu:%s\n' "$chat_id"
  exit 0
fi

exec /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main \
  --profile hermeskevin send --to "feishu:$chat_id" --file - --quiet
