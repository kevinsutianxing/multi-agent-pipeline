#!/usr/bin/env python3
"""Flush durable notifications through an exact-target sender command."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from reliable_pipeline import ReliablePipeline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--command", nargs=argparse.REMAINDER, required=True)
    args = parser.parse_args()
    if not args.command:
        raise SystemExit("--command requires a sender command")

    pipeline = ReliablePipeline(args.db, runs_dir=args.runs_dir)
    failed = False
    delivered = 0
    for notification in pipeline.pending_notifications():
        payload = notification["payload"] or json.dumps(
            {
                "run_id": notification["run_id"],
                "kind": notification["kind"],
                "target": notification["target"],
                "message": notification["kind"],
            },
            ensure_ascii=False,
        )
        try:
            result = subprocess.run(
                args.command,
                input=payload + "\n",
                text=True,
                capture_output=True,
                timeout=args.timeout,
                check=False,
            )
        except Exception as error:
            pipeline.mark_notification(notification["run_id"], notification["kind"], error=str(error))
            failed = True
            continue
        if result.returncode == 0:
            pipeline.mark_notification(notification["run_id"], notification["kind"])
            delivered += 1
        else:
            detail = result.stderr.strip() or result.stdout.strip() or f"sender exit={result.returncode}"
            pipeline.mark_notification(notification["run_id"], notification["kind"], error=detail)
            failed = True
    print(json.dumps({"delivered": delivered, "failed": failed}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
