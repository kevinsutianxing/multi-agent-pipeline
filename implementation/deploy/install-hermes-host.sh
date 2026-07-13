#!/usr/bin/env bash
set -euo pipefail

STAGE_ROOT=${1:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}
HERMES_HOME=${HERMES_HOME:-/home/ubuntu/.hermes}
LOCAL_BIN=${HOME}/.local/bin
PLUGIN_DIR="$HERMES_HOME/plugins/reliable_research_ingress"
SERVICE=${HERMES_GATEWAY_SERVICE:-hermes-gateway.service}
REMOTE_HOST=${PIPELINE_REMOTE_HOST:-sz81}
REMOTE_ROOT=${PIPELINE_REMOTE_ROOT:-/home/ubuntu/multi-agent-pipeline/implementation}
REMOTE_DB=${PIPELINE_REMOTE_DB:-$REMOTE_ROOT/state/pipeline.db}

install -d "$PLUGIN_DIR" "$LOCAL_BIN"
install -m 0644 "$STAGE_ROOT/plugins/reliable_research_ingress/plugin.yaml" "$PLUGIN_DIR/plugin.yaml"
install -m 0644 "$STAGE_ROOT/plugins/reliable_research_ingress/__init__.py" "$PLUGIN_DIR/__init__.py"
install -m 0755 "$STAGE_ROOT/scripts/hermescold-pipeline-worker.py" "$LOCAL_BIN/hermescold-pipeline-worker.py"
install -m 0755 "$STAGE_ROOT/scripts/hermeskevin-pipeline-notify.py" "$LOCAL_BIN/hermeskevin-pipeline-notify.py"

if command -v hermes >/dev/null 2>&1; then
  hermes plugins enable reliable_research_ingress >/dev/null 2>&1 || true
fi

HERMES_PYTHON=${HERMES_PYTHON:-$HERMES_HOME/hermes-agent/venv/bin/python}
if [[ -x "$HERMES_PYTHON" ]]; then
  "$HERMES_PYTHON" - "$HERMES_HOME/config.yaml" <<'PY'
from pathlib import Path
import sys
try:
    import yaml
except ImportError:
    raise SystemExit(0)
path = Path(sys.argv[1])
data = yaml.safe_load(path.read_text()) if path.exists() else {}
if not isinstance(data, dict):
    data = {}
plugins = data.setdefault("plugins", {})
enabled = plugins.setdefault("enabled", [])
if "reliable_research_ingress" not in enabled:
    enabled.append("reliable_research_ingress")
disabled = plugins.get("disabled")
if isinstance(disabled, list) and "reliable_research_ingress" in disabled:
    disabled.remove("reliable_research_ingress")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
PY
fi

DROPIN="$HOME/.config/systemd/user/$SERVICE.d"
install -d "$DROPIN"
cat > "$DROPIN/pipeline.conf" <<EOF
[Service]
Environment=PIPELINE_REMOTE_HOST=$REMOTE_HOST
Environment=PIPELINE_REMOTE_ROOT=$REMOTE_ROOT
Environment=PIPELINE_REMOTE_DB=$REMOTE_DB
EOF

systemctl --user daemon-reload || true
systemctl --user try-restart "$SERVICE" || true

echo "Hermes plugin installed: $PLUGIN_DIR"
echo "Gateway service restart attempted: $SERVICE"
