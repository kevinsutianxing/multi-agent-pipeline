#!/usr/bin/env python3
"""Run hermescold as a constrained JSON-only stage executor."""
from __future__ import annotations

import json
import subprocess
import sys


def main() -> int:
    request = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}
    prompt = request.get("prompt") or ""
    if not prompt:
        prompt = sys.argv[1] if len(sys.argv) > 1 else ""
    if not prompt:
        raise SystemExit("A stage prompt is required")
    command = [
        "/home/ubuntu/.hermes/hermes-agent/venv/bin/python", "-m", "hermes_cli.main",
        "--profile", "hermescold", "chat", "-Q", "--source", "tool",
        "--skills", "hermescold-tech-research", "--max-turns", "20", "-q", prompt,
    ]
    result = subprocess.run(command, text=True, capture_output=True, timeout=900)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode
    sys.stdout.write(result.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
