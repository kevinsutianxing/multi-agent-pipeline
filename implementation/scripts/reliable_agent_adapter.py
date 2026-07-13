#!/usr/bin/env python3
"""Stateless live-agent adapter for reliable_worker --command.

Reads one job JSON from stdin and prints only the agent's raw response.  It is
intentionally unable to access the pipeline database or mutate pipeline state.
"""
from __future__ import annotations

import json
import subprocess
import sys


ROLE = {"QUALIFY": "codex", "ACQUIRE": "hermescold", "VALIDATE": "deterministic", "ANALYZE": "hermescold", "REVIEW": "claude", "DELIVER": "codex"}


def main() -> int:
    job = json.loads(sys.stdin.read())
    stage, role = job["stage"], ROLE[job["stage"]]
    prompt = (f"Return ONLY one JSON object with stage={stage!r} and an evidence array. "
              "Do not claim facts without evidence; include limitations in evidence when needed.")
    if role == "deterministic":
        print(json.dumps({"stage": stage, "evidence": [{"kind": "deterministic_gate"}]})); return 0
    if role == "codex":
        command, input_text = ["ssh", "hk43", "codex", "exec", "--ephemeral", "--sandbox", "read-only", "-"], prompt
    elif role == "claude":
        command, input_text = ["claude", "--safe-mode", "--print", "--output-format", "text", "--permission-mode", "plan", prompt], ""
    else:
        command, input_text = ["ssh", "hk43", "/home/ubuntu/.local/bin/hermescold-pipeline-worker.py"], json.dumps({"prompt": prompt})
    result = subprocess.run(command, input=input_text, text=True, capture_output=True, timeout=900)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
