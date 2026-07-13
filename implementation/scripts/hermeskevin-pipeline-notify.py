#!/usr/bin/env python3
"""Send one durable notification to its recorded Hermes target."""
from __future__ import annotations

import json
import os
import subprocess
import sys


def main() -> int:
    payload = json.loads(sys.stdin.read())
    target = str(payload.get("target") or "")
    message = str(payload.get("message") or "")
    if not target.startswith("feishu:") or not message:
        raise SystemExit("notification requires a Feishu target and non-empty message")
    hermes_python = os.environ.get("HERMES_PYTHON", "/home/ubuntu/.hermes/hermes-agent/venv/bin/python")
    profile = os.environ.get("PIPELINE_HERMES_NOTIFY_PROFILE", "hermeskevin")
    result = subprocess.run(
        [
            hermes_python,
            "-m",
            "hermes_cli.main",
            "--profile",
            profile,
            "send",
            "--to",
            target,
            "--quiet",
            message,
        ],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
