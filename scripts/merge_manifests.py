#!/usr/bin/env python3
"""Merge segmented source manifests without using an LLM.

Parallel acquisition workers write source_manifest.<name>.json. This command
combines their source/evidence records into source_manifest.json in stable order.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


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
        path for path in run_dir.glob("source_manifest.*.json")
        if path.name != "source_manifest.json"
    )
    if not segments:
        raise FileNotFoundError("no source_manifest.<name>.json segments found")

    records: list[dict[str, Any]] = []
    inputs: list[str] = []
    for path in segments:
        value = json.loads(path.read_text(encoding="utf-8"))
        records.extend(extract_records(value))
        inputs.append(path.name)

    records.sort(key=lambda item: str(item.get("evidence_id") or item.get("source_id") or ""))
    output = {"version": 1, "inputs": inputs, "sources": records}
    target = run_dir / "source_manifest.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "MERGED", "output": str(target), "segments": len(segments), "records": len(records)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge parallel source manifest segments")
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    result = merge(args.run_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
