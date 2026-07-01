#!/usr/bin/env python3
"""Merge segmented source and dataset manifests without using an LLM.

Parallel acquisition workers write ``source_manifest.<name>.json`` and
``dataset_manifest.<name>.json``. This command combines both families in stable
order and rejects conflicting duplicate identifiers before the data gate runs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts import merge_dataset_manifests


def extract_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("sources", "evidence", "records"):
            records = value.get(key)
            if isinstance(records, list):
                return [item for item in records if isinstance(item, dict)]
    raise ValueError("manifest must be a list or contain sources/evidence/records list")


def merge(run_dir: Path) -> dict[str, Any]:
    segments = sorted(
        path
        for path in run_dir.glob("source_manifest.*.json")
        if path.name != "source_manifest.json"
    )
    if not segments:
        raise FileNotFoundError("no source_manifest.<name>.json segments found")

    by_id: dict[str, dict[str, Any]] = {}
    inputs: list[str] = []
    for path in segments:
        value = json.loads(path.read_text(encoding="utf-8"))
        for record in extract_records(value):
            record_id = str(record.get("evidence_id") or record.get("source_id") or "")
            if not record_id:
                raise ValueError(f"source/evidence record in {path.name} lacks an ID")
            if record_id in by_id and by_id[record_id] != record:
                raise ValueError(f"conflicting duplicate source/evidence ID: {record_id}")
            by_id[record_id] = record
        inputs.append(path.name)

    records = [by_id[key] for key in sorted(by_id)]
    output = {"version": 1, "inputs": inputs, "sources": records}
    target = run_dir / "source_manifest.json"
    target.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result: dict[str, Any] = {
        "status": "MERGED",
        "source_output": str(target),
        "source_segments": len(segments),
        "source_records": len(records),
    }

    dataset_segments = sorted(
        path
        for path in run_dir.glob("dataset_manifest.*.json")
        if path.name != "dataset_manifest.json"
    )
    if dataset_segments:
        dataset_result = merge_dataset_manifests.merge(run_dir)
        result["dataset_output"] = dataset_result["output"]
        result["dataset_segments"] = dataset_result["segments"]
        result["dataset_records"] = dataset_result["records"]
    elif not (run_dir / "dataset_manifest.json").is_file():
        raise FileNotFoundError(
            "no dataset_manifest.<name>.json segments or existing dataset_manifest.json found"
        )
    else:
        result["dataset_output"] = str(run_dir / "dataset_manifest.json")
        result["dataset_segments"] = 0
        result["dataset_records"] = None

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge parallel source and dataset manifest segments"
    )
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    result = merge(args.run_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
