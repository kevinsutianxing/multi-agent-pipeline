#!/usr/bin/env python3
"""Lease-aware worker for the durable research pipeline."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from reliable_pipeline import ReliablePipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path)
    parser.add_argument("--max-attempts", type=int, default=int(os.environ.get("PIPELINE_MAX_ATTEMPTS", "3")))
    parser.add_argument("--lease-seconds", type=int, default=int(os.environ.get("PIPELINE_LEASE_SECONDS", "1200")))
    parser.add_argument("--heartbeat-seconds", type=int, default=int(os.environ.get("PIPELINE_HEARTBEAT_SECONDS", "30")))
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("PIPELINE_AGENT_TIMEOUT_SECONDS", "900")))
    parser.add_argument("--drain", type=int, default=1, help="Maximum jobs to process before exiting")
    parser.add_argument("--command", nargs=argparse.REMAINDER, required=True)
    return parser.parse_args()


def execute_job(
    pipeline: ReliablePipeline,
    job: dict[str, Any],
    worker_id: str,
    command: list[str],
    *,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout: int,
) -> dict[str, Any]:
    payload = json.dumps(
        {
            "job_id": job["id"],
            "run_id": job["run_id"],
            "stage": job["stage"],
            "attempt": job["attempts"],
            "context": job["context"],
        },
        ensure_ascii=False,
    )
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    elapsed = 0
    stdout = ""
    stderr = ""
    pending_input: str | None = payload
    while True:
        wait_for = min(heartbeat_seconds, max(1, timeout - elapsed))
        try:
            stdout, stderr = process.communicate(input=pending_input, timeout=wait_for)
            break
        except subprocess.TimeoutExpired:
            pending_input = None
            elapsed += wait_for
            if elapsed >= timeout:
                process.kill()
                stdout, stderr = process.communicate()
                return pipeline.finish(job["id"], worker_id, stdout or "", exit_code=124)
            if not pipeline.heartbeat(job["id"], worker_id, lease_seconds=lease_seconds):
                process.kill()
                process.communicate()
                return {"accepted": False, "reason": "lease_lost"}
    result = pipeline.finish(job["id"], worker_id, stdout or "", exit_code=process.returncode or 0)
    if stderr:
        result["adapter_stderr"] = stderr[-4000:]
    return result


def main() -> int:
    args = parse_args()
    if not args.command:
        raise SystemExit("--command requires an adapter command")
    pipeline = ReliablePipeline(args.db, max_attempts=args.max_attempts, runs_dir=args.runs_dir)
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    results: list[dict[str, Any]] = []
    for _ in range(max(1, args.drain)):
        job = pipeline.claim(worker_id, lease_seconds=args.lease_seconds)
        if not job:
            break
        try:
            outcome = execute_job(
                pipeline,
                job,
                worker_id,
                args.command,
                lease_seconds=args.lease_seconds,
                heartbeat_seconds=args.heartbeat_seconds,
                timeout=args.timeout,
            )
        except Exception as error:
            outcome = pipeline.finish(job["id"], worker_id, "", exit_code=70)
            outcome["worker_error"] = str(error)
        results.append({"run_id": job["run_id"], "stage": job["stage"], "outcome": outcome})
    print(json.dumps({"worker_id": worker_id, "processed": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
