#!/usr/bin/env bash
set -euo pipefail

readonly ROOT=/home/ubuntu/multi-agent-pipeline
readonly CONTROLLER="$ROOT/scripts/researchctl.py"

python3 "$CONTROLLER" watch --all >/dev/null

for alert_path in "$ROOT"/runs/*/alert.json; do
  [[ -f "$alert_path" ]] || continue
  run_id=$(jq -r '.run_id' "$alert_path")
  delivered_at=$(jq -r '.delivered_at // empty' "$alert_path")
  [[ -z "$delivered_at" ]] || continue
  message=$(jq -r '"[研究流程阻断] run=\(.run_id) | stage=\(.stage) | status=\(.status)\n原因：\(.reason)\n已停止继续交付；请查看 SZ81 的 runs/\(.run_id)/handoff.json 并决定下一步。"' "$alert_path")
  if printf '%s\n' "$message" | ssh hk43 /home/ubuntu/.local/bin/hermeskevin-pipeline-notify.sh; then
    python3 "$CONTROLLER" mark-alert-delivered "$run_id" >/dev/null
  fi
done
