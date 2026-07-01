#!/usr/bin/env python3
"""Merge segmented dataset manifests without using an LLM."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def extract_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("datasets", "records"):
            records = value.get(key)
            if isinstance(records, list):
                return [item for item in records if isinstance(item, dict)]
    raise ValueError("manifest must be a list or contain datasets/records list")


def merge(run_dir: Path) -> dict[str, Any]:
    segments = sorted(
        path
        for path in run_dir.glob("dataset_manifest.*.json")
        if path.name != "dataset_manifest.json"
    )
    if not segments:
        raise FileNotFoundError("no dataset_manifest.<name>.json segments found")

    by_id: dict[str, dict[str, Any]] = {}
    inputs: list[str] = []
    for path in segments:
        value = json.loads(path.read_text(encoding="utf-8"))
        for record in extract_records(value):
            dataset_id = str(record.get("dataset_id") or "")
            if not dataset_id:
                raise ValueError(f"dataset record in {path.name} lacks dataset_id")
            if dataset_id in by_id and by_id[dataset_id] != record:
                raise ValueError(f"conflicting duplicate dataset_id: {dataset_id}")
            by_id[dataset_id] = record
        inputs.append(path.name)

    records = [by_id[key] for key in sorted(by_id)]
    output = {"version": 1, "inputs": inputs, "datasets": records}
    target = run_dir / "dataset_manifest.json"
    target.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "MERGED",
        "output": str(target),
        "segments": len(segments),
        "records": len(records),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge parallel dataset manifest segments")
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    result = merge(args.run_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
