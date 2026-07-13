#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
ENV_FILE=${PIPELINE_ENV_FILE:-/etc/multi-agent-pipeline.env}
SERVICE_DIR=${PIPELINE_SYSTEMD_DIR:-/etc/systemd/system}
RUN_USER=${PIPELINE_RUN_USER:-ubuntu}
RUN_GROUP=${PIPELINE_RUN_GROUP:-ubuntu}

[[ $EUID -eq 0 ]] || { echo "Run with sudo: $0" >&2; exit 2; }

install -d -o "$RUN_USER" -g "$RUN_GROUP" "$ROOT/state" "$ROOT/state/runs"
chmod 0755 "$ROOT/scripts/"*.py

if [[ ! -f "$ENV_FILE" ]]; then
  install -m 0644 "$ROOT/config/pipeline.env.example" "$ENV_FILE"
fi

python3 - "$ENV_FILE" "$ROOT" <<'PY'
from pathlib import Path
import sys
path, root = Path(sys.argv[1]), sys.argv[2]
updates = {
    "PIPELINE_ROOT": root,
    "PIPELINE_DB": f"{root}/state/pipeline.db",
    "PIPELINE_RUNS_DIR": f"{root}/state/runs",
}
lines = path.read_text().splitlines() if path.exists() else []
seen = set()
out = []
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        key = line.split("=", 1)[0]
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
    out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out).rstrip() + "\n")
PY

for unit in multi-agent-pipeline-worker.service multi-agent-pipeline-worker.timer multi-agent-pipeline-notify.service multi-agent-pipeline-notify.timer; do
  install -m 0644 "$ROOT/systemd/$unit" "$SERVICE_DIR/$unit"
done

systemctl disable --now multi-agent-pipeline-watchdog.timer 2>/dev/null || true
systemctl disable --now multi-agent-pipeline-watchdog.service 2>/dev/null || true
rm -f "$SERVICE_DIR/multi-agent-pipeline-watchdog.timer" "$SERVICE_DIR/multi-agent-pipeline-watchdog.service"

systemctl daemon-reload
systemctl enable --now multi-agent-pipeline-worker.timer multi-agent-pipeline-notify.timer
systemctl start multi-agent-pipeline-worker.service multi-agent-pipeline-notify.service || true

echo "Controller installed at $ROOT"
echo "Configuration: $ENV_FILE"
