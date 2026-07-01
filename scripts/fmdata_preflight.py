#!/usr/bin/env python3
"""Fail-closed preflight for the fmdata research data plane."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from adapters.fmdata_client import FMDataClient, FMDataError


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    dataset: str | None = None


def load_requirements(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("datasets")
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("requirements must be a list or an object with a datasets list")
    return value


def evaluate(
    client: FMDataClient,
    requirements: list[dict[str, Any]],
) -> dict[str, Any]:
    findings: list[Finding] = []

    if not client.research_key:
        findings.append(
            Finding(
                "CRITICAL",
                "MISSING_RESEARCH_KEY",
                "FMDATA_RESEARCH_KEY is required for the research API",
            )
        )

    try:
        health = client.health()
    except FMDataError as exc:
        health = {}
        findings.append(Finding("CRITICAL", "HEALTH_FAILED", str(exc)))

    if health:
        if health.get("status") != "ok":
            findings.append(
                Finding("CRITICAL", "HEALTH_NOT_OK", f"health status is {health.get('status')!r}")
            )
        if health.get("contract") != "research-snapshot-v1":
            findings.append(
                Finding(
                    "CRITICAL",
                    "CONTRACT_MISMATCH",
                    f"expected research-snapshot-v1, got {health.get('contract')!r}",
                )
            )
        if health.get("self_validation") is not False:
            findings.append(
                Finding(
                    "CRITICAL",
                    "SELF_VALIDATION_NOT_DISABLED",
                    "fmdata must not claim authority to validate its own snapshots",
                )
            )

    try:
        catalog = client.catalog() if not any(f.code == "MISSING_RESEARCH_KEY" for f in findings) else {}
    except FMDataError as exc:
        catalog = {}
        findings.append(Finding("CRITICAL", "CATALOG_FAILED", str(exc)))

    datasets = catalog.get("datasets") if isinstance(catalog, dict) else None
    if catalog and not isinstance(datasets, dict):
        findings.append(
            Finding("CRITICAL", "INVALID_CATALOG", "catalog.datasets is not an object")
        )
        datasets = {}
    datasets = datasets or {}

    for requirement in requirements:
        name = str(requirement.get("dataset") or requirement.get("name") or "")
        if not name:
            findings.append(
                Finding("CRITICAL", "INVALID_REQUIREMENT", "dataset requirement lacks a name")
            )
            continue
        record = datasets.get(name)
        if not isinstance(record, dict):
            findings.append(
                Finding("CRITICAL", "DATASET_NOT_FOUND", "required dataset is not registered", name)
            )
            continue
        if int(record.get("rows") or 0) <= 0:
            findings.append(
                Finding("CRITICAL", "DATASET_EMPTY", "required dataset has no rows", name)
            )
        if requirement.get("research_ready", True) and record.get("research_ready") is not True:
            findings.append(
                Finding(
                    "CRITICAL",
                    "DATASET_NOT_RESEARCH_READY",
                    f"semantic limitations: {record.get('limitations') or []}",
                    name,
                )
            )
        semantics = record.get("semantics") if isinstance(record.get("semantics"), dict) else {}
        for field, expected in (requirement.get("expected_semantics") or {}).items():
            actual = semantics.get(field)
            if actual != expected:
                findings.append(
                    Finding(
                        "CRITICAL",
                        "SEMANTIC_MISMATCH",
                        f"{field}: expected {expected!r}, got {actual!r}",
                        name,
                    )
                )

    critical = sum(item.severity == "CRITICAL" for item in findings)
    return {
        "status": "PASS" if critical == 0 else "FAIL",
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "service": {
            "base_url": client.base_url,
            "health": health,
            "catalog_dataset_count": len(datasets),
        },
        "requirements": requirements,
        "summary": {"critical_count": critical, "dataset_requirements": len(requirements)},
        "findings": [asdict(item) for item in findings],
        "preflight": {"name": "fmdata_preflight.py", "version": 1},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate fmdata research-plane readiness")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--requirements", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()

    try:
        requirements = load_requirements(args.requirements)
        report = evaluate(FMDataClient(base_url=args.base_url), requirements)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "status": "FAIL",
            "summary": {"critical_count": 1},
            "findings": [
                asdict(Finding("CRITICAL", "PREFLIGHT_INPUT_ERROR", str(exc)))
            ],
        }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
