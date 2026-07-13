#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
ENV_FILE=${PIPELINE_ENV_FILE:-/etc/multi-agent-pipeline.env}
HERMES_HOST=${HERMES_HOST:-hk43}

[[ -f "$ENV_FILE" ]] && set -a && source "$ENV_FILE" && set +a
PIPELINE_DB=${PIPELINE_DB:-$ROOT/state/pipeline.db}
PIPELINE_RUNS_DIR=${PIPELINE_RUNS_DIR:-$ROOT/state/runs}

python3 "$ROOT/scripts/reliable_ctl.py" \
  --db "$PIPELINE_DB" \
  --runs-dir "$PIPELINE_RUNS_DIR" \
  health

systemctl is-enabled --quiet multi-agent-pipeline-worker.timer
systemctl is-active --quiet multi-agent-pipeline-worker.timer
systemctl is-enabled --quiet multi-agent-pipeline-notify.timer
systemctl is-active --quiet multi-agent-pipeline-notify.timer

ssh -o BatchMode=yes "$HERMES_HOST" 'test -f ~/.hermes/plugins/reliable_research_ingress/plugin.yaml'
ssh -o BatchMode=yes "$HERMES_HOST" 'test -x ~/.local/bin/hermescold-pipeline-worker.py'
ssh -o BatchMode=yes "$HERMES_HOST" 'test -x ~/.local/bin/hermeskevin-pipeline-notify.py'
ssh -o BatchMode=yes "$HERMES_HOST" 'command -v codex >/dev/null'

if ! command -v claude >/dev/null 2>&1; then
  echo "warning: claude command is not available on the controller host; REVIEW stages will retry/block until PIPELINE_CLAUDE_CMD is corrected" >&2
fi

ssh -o BatchMode=yes "$HERMES_HOST" "ssh -o BatchMode=yes ${PIPELINE_REMOTE_HOST:-sz81} 'test -f ${PIPELINE_DB}'" || {
  echo "warning: reverse SSH/database reachability check failed; verify HK43 -> SZ81 alias and permissions" >&2
}

echo "healthcheck passed"
