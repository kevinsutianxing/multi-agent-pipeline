#!/usr/bin/env python3
"""Invoke the hermescold profile as a stateless pipeline stage executor."""
from __future__ import annotations

import json
import os
import subprocess
import sys


def main() -> int:
    request = json.loads(sys.stdin.read())
    prompt = str(request.get("prompt") or "")
    if not prompt:
        raise SystemExit("a non-empty prompt is required")
    hermes_python = os.environ.get("HERMES_PYTHON", "/home/ubuntu/.hermes/hermes-agent/venv/bin/python")
    profile = os.environ.get("PIPELINE_HERMESCOLD_PROFILE", "hermescold")
    skill = os.environ.get("PIPELINE_HERMESCOLD_SKILL", "hermescold-tech-research")
    result = subprocess.run(
        [
            hermes_python,
            "-m",
            "hermes_cli.main",
            "--profile",
            profile,
            "chat",
            "-Q",
            "--source",
            "tool",
            "--skills",
            skill,
            "--max-turns",
            os.environ.get("PIPELINE_HERMESCOLD_MAX_TURNS", "20"),
            "-q",
            prompt,
        ],
        text=True,
        capture_output=True,
        timeout=int(os.environ.get("PIPELINE_AGENT_TIMEOUT_SECONDS", "900")),
        check=False,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
