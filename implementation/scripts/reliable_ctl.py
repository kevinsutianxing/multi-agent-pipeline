#!/usr/bin/env python3
"""Operator CLI for reliable pipeline-v2."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from reliable_pipeline import ReliablePipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("/home/ubuntu/multi-agent-pipeline/state/reliable-v2.db"))
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--request-key", required=True)
    create.add_argument("--question", required=True)
    status = commands.add_parser("status")
    status.add_argument("run_id")
    args = parser.parse_args()
    pipeline = ReliablePipeline(args.db)
    if args.command == "create":
        print(json.dumps({"run_id": pipeline.create(args.request_key, args.question)}))
        return 0
    with pipeline.db() as connection:
        row = connection.execute("SELECT * FROM runs WHERE id=?", (args.run_id,)).fetchone()
        if not row:
            raise SystemExit("unknown run")
        print(json.dumps(dict(row)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
