#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 create --question '...' [--research-type deep_research] | status RUN_ID"
}

case "${1:-}" in
  create)
    shift
    research_type="deep_research"
    question=""
    while (($#)); do
      case "$1" in
        --question) question="$2"; shift 2 ;;
        --research-type) research_type="$2"; shift 2 ;;
        *) usage; exit 2 ;;
      esac
    done
    [[ -n "$question" ]] || { echo "--question is required" >&2; exit 2; }
    printf '%s' "$question" | ssh sz81 \
      "python3 /home/ubuntu/multi-agent-pipeline/scripts/researchctl.py create --question-stdin --research-type '$research_type' --requester hermeskevin"
    ;;
  status)
    [[ $# -eq 2 ]] || { usage; exit 2; }
    ssh sz81 "python3 /home/ubuntu/multi-agent-pipeline/scripts/researchctl.py status '$2'"
    ;;
  *) usage; exit 2 ;;
esac
