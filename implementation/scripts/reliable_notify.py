#!/usr/bin/env python3
"""Deliver durable pipeline-v2 notifications; mark sent only after success."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from reliable_pipeline import ReliablePipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--command", nargs=argparse.REMAINDER, required=True)
    args = parser.parse_args()
    pipeline = ReliablePipeline(args.db)
    failed = False
    for notification in pipeline.pending_notifications():
        message = f"[可靠研究管道] run={notification['run_id']} | {notification['kind']}"
        if notification["kind"].startswith("EVENT:"):
            event_id = notification["kind"].split(":", 1)[1]
            with pipeline.db() as connection:
                event = connection.execute("SELECT kind,detail,created_at FROM events WHERE id=?", (event_id,)).fetchone()
            if event:
                message = f"[可靠研究管道] {event['kind']} | run={notification['run_id']} | {event['detail']} | {event['created_at']}"
        result = subprocess.run(args.command, input=message + "\n", text=True, capture_output=True)
        if result.returncode == 0:
            pipeline.mark_notified(notification["run_id"], notification["kind"])
        else:
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
