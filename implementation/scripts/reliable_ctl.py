#!/usr/bin/env python3
"""Operator CLI for the durable research pipeline."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from reliable_pipeline import ReliablePipeline


def pipeline_from(args: argparse.Namespace) -> ReliablePipeline:
    return ReliablePipeline(
        args.db,
        max_attempts=args.max_attempts,
        runs_dir=args.runs_dir,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path)
    parser.add_argument("--max-attempts", type=int, default=3)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create")
    create.add_argument("--request-key")
    create.add_argument("--question")
    create.add_argument("--question-stdin", action="store_true")
    create.add_argument("--requester", default="manual")
    create.add_argument("--notify-target")

    for name in ("status", "context", "retry"):
        commands.add_parser(name).add_argument("run_id")
    listing = commands.add_parser("list")
    listing.add_argument("--limit", type=int, default=20)
    commands.add_parser("health")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pipeline = pipeline_from(args)
    result: Any
    if args.command == "create":
        question = sys.stdin.read() if args.question_stdin else (args.question or "")
        request_key = args.request_key or hashlib.sha256(
            f"{args.requester}\0{args.notify_target or ''}\0{question.strip()}".encode()
        ).hexdigest()
        result = {
            "run_id": pipeline.create(
                request_key,
                question,
                requester=args.requester,
                notify_target=args.notify_target,
            )
        }
    elif args.command == "status":
        result = pipeline.status(args.run_id)
    elif args.command == "context":
        result = pipeline.context(args.run_id)
    elif args.command == "retry":
        result = pipeline.retry(args.run_id)
    elif args.command == "list":
        result = pipeline.list_runs(args.limit)
    else:
        result = pipeline.health()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
