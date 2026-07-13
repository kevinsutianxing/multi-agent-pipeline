#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
HERMES_HOST=${HERMES_HOST:-hk43}
CONTROLLER_ALIAS=${PIPELINE_REMOTE_HOST:-sz81}
REMOTE_ROOT=${PIPELINE_REMOTE_ROOT:-/home/ubuntu/multi-agent-pipeline/implementation}
REMOTE_DB=${PIPELINE_REMOTE_DB:-$REMOTE_ROOT/state/pipeline.db}
STAGE=/tmp/multi-agent-pipeline-install

python3 -m compileall -q "$ROOT/scripts" "$ROOT/plugins" "$ROOT/tests"
python3 -m unittest discover -s "$ROOT/tests" -v
bash -n "$ROOT/deploy/"*.sh

sudo "$ROOT/deploy/install-controller.sh"

tar -C "$ROOT" -czf - \
  plugins/reliable_research_ingress \
  scripts/hermescold-pipeline-worker.py \
  scripts/hermeskevin-pipeline-notify.py \
  deploy/install-hermes-host.sh \
| ssh -o BatchMode=yes "$HERMES_HOST" "rm -rf '$STAGE' && mkdir -p '$STAGE' && tar -xzf - -C '$STAGE'"

ssh -o BatchMode=yes "$HERMES_HOST" \
  "PIPELINE_REMOTE_HOST='$CONTROLLER_ALIAS' PIPELINE_REMOTE_ROOT='$REMOTE_ROOT' PIPELINE_REMOTE_DB='$REMOTE_DB' bash '$STAGE/deploy/install-hermes-host.sh' '$STAGE'"

"$ROOT/deploy/healthcheck.sh"

echo "Deployment completed. Trigger format: 启动多智能体研究：<question>"
