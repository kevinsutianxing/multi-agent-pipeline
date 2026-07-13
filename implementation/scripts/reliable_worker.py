#!/usr/bin/env python3
"""Single-job worker boundary for reliable_pipeline; adapters plug in here."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from reliable_pipeline import ReliablePipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--fake", action="store_true", help="Emit a valid deterministic artifact for integration tests")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--command", nargs=argparse.REMAINDER, help="Adapter command; receives one job JSON on stdin")
    args = parser.parse_args()
    pipeline = ReliablePipeline(args.db)
    pipeline.recover_running()
    job = pipeline.claim()
    if not job:
        print("idle")
        return 0
    if args.command:
        payload = json.dumps({"job_id": job["id"], "run_id": job["run_id"], "stage": job["stage"]})
        try:
            result = subprocess.run(args.command, input=payload, text=True, capture_output=True, timeout=args.timeout)
            pipeline.finish(job["id"], result.stdout, exit_code=result.returncode)
            print(json.dumps({"job_id": job["id"], "exit_code": result.returncode}))
            return result.returncode
        except subprocess.TimeoutExpired as error:
            pipeline.finish(job["id"], error.stdout or "", exit_code=124)
            print(json.dumps({"job_id": job["id"], "exit_code": 124, "error": "timeout"}))
            return 124
    if not args.fake:
        pipeline.finish(job["id"], "", exit_code=75)
        print("no live adapter configured")
        return 75
    pipeline.finish(job["id"], json.dumps({"stage": job["stage"], "evidence": [{"source": "fake"}]}))
    print(json.dumps({"job_id": job["id"], "stage": job["stage"], "status": "submitted"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
