#!/usr/bin/env python3
"""Deterministic evidence gate for financial-research runs.

This validator uses only the Python standard library. It verifies preserved
source snapshots and hashes, point-in-time dates, dataset metadata, calculation
lineage, and claim-level evidence coverage.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
CLAIM_CLASSES = {"FACT", "CALCULATION", "INFERENCE", "HYPOTHESIS", "SCENARIO"}
VERIFICATION_STATUSES = {"VERIFIED", "PARTIAL", "CONFLICTED", "NOT_VERIFIED"}


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    path: str | None = None
    record_id: str | None = None


def parse_date(
    value: Any,
    field: str,
    findings: list[Finding],
    *,
    path: str,
    record_id: str | None,
) -> dt.date | None:
    if value in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        findings.append(
            Finding(
                "CRITICAL",
                "INVALID_DATE",
                f"{field} is not ISO date/datetime: {value!r}",
                path,
                record_id,
            )
        )
        return None


def load_json(path: Path, findings: list[Finding], required: bool = True) -> Any:
    if not path.exists():
        if required:
            findings.append(
                Finding("CRITICAL", "MISSING_FILE", f"Required file is missing: {path.name}", str(path))
            )
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        findings.append(Finding("CRITICAL", "INVALID_JSON", f"Cannot parse {path.name}: {exc}", str(path)))
        return None


def load_jsonl(path: Path, findings: list[Finding], required: bool = True) -> list[dict[str, Any]]:
    if not path.exists():
        if required:
            findings.append(
                Finding("CRITICAL", "MISSING_FILE", f"Required file is missing: {path.name}", str(path))
            )
        return []
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            findings.append(Finding("CRITICAL", "INVALID_JSONL", f"Line {line_no}: {exc}", str(path)))
            continue
        if not isinstance(value, dict):
            findings.append(Finding("CRITICAL", "INVALID_RECORD", f"Line {line_no} is not an object", str(path)))
            continue
        rows.append(value)
    return rows


def records_from_manifest(value: Any, candidate_keys: Iterable[str]) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in candidate_keys:
            candidate = value.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
    return []


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_fields(
    record: dict[str, Any],
    fields: Iterable[str],
    findings: list[Finding],
    *,
    manifest_path: Path,
    record_id: str,
) -> None:
    for field in fields:
        if record.get(field) in (None, "", []):
            findings.append(
                Finding(
                    "CRITICAL",
                    "MISSING_FIELD",
                    f"Missing required field: {field}",
                    str(manifest_path),
                    record_id,
                )
            )


def resolve_snapshot(run_dir: Path, relative_path: str, findings: list[Finding], manifest_path: Path, record_id: str) -> Path | None:
    snapshot = (run_dir / relative_path).resolve()
    try:
        snapshot.relative_to(run_dir.resolve())
    except ValueError:
        findings.append(
            Finding(
                "CRITICAL",
                "PATH_ESCAPE",
                f"Referenced path escapes run directory: {relative_path}",
                str(manifest_path),
                record_id,
            )
        )
        return None
    return snapshot


def validate_snapshot_hash(
    run_dir: Path,
    relative_path: Any,
    expected_hash: Any,
    findings: list[Finding],
    *,
    manifest_path: Path,
    record_id: str,
    missing_code: str,
) -> None:
    if not relative_path:
        return
    snapshot = resolve_snapshot(run_dir, str(relative_path), findings, manifest_path, record_id)
    if snapshot is None:
        return
    expected = str(expected_hash or "")
    if not snapshot.is_file():
        findings.append(
            Finding("CRITICAL", missing_code, f"Snapshot does not exist: {relative_path}", str(manifest_path), record_id)
        )
    elif not SHA256_RE.fullmatch(expected):
        findings.append(
            Finding(
                "CRITICAL",
                "INVALID_SHA256",
                "Expected SHA-256 must be 64 hexadecimal characters",
                str(manifest_path),
                record_id,
            )
        )
    elif sha256_file(snapshot).lower() != expected.lower():
        findings.append(
            Finding("CRITICAL", "HASH_MISMATCH", f"Snapshot hash mismatch: {relative_path}", str(manifest_path), record_id)
        )


def validate_sources(run_dir: Path, as_of: dt.date, findings: list[Finding]) -> set[str]:
    path = run_dir / "source_manifest.json"
    raw = load_json(path, findings)
    records = records_from_manifest(raw, ("sources", "evidence", "records"))
    if raw is not None and not records:
        findings.append(Finding("CRITICAL", "EMPTY_SOURCE_MANIFEST", "No source/evidence records found", str(path)))

    seen: set[str] = set()
    required = (
        "source_id",
        "provider",
        "locator",
        "retrieved_at",
        "as_of",
        "snapshot_path",
        "content_sha256",
    )
    for record in records:
        record_id = str(record.get("evidence_id") or record.get("source_id") or "<unknown>")
        require_fields(record, required, findings, manifest_path=path, record_id=record_id)
        evidence_id = str(record.get("evidence_id") or record.get("source_id") or "")
        if evidence_id:
            if evidence_id in seen:
                findings.append(
                    Finding("CRITICAL", "DUPLICATE_EVIDENCE_ID", f"Duplicate evidence ID: {evidence_id}", str(path), evidence_id)
                )
            seen.add(evidence_id)

        record_as_of = parse_date(record.get("as_of"), "as_of", findings, path=str(path), record_id=record_id)
        available_at = parse_date(record.get("available_at"), "available_at", findings, path=str(path), record_id=record_id)
        published_at = parse_date(record.get("published_at"), "published_at", findings, path=str(path), record_id=record_id)
        if record_as_of and record_as_of > as_of:
            findings.append(
                Finding(
                    "CRITICAL",
                    "SOURCE_ASOF_IN_FUTURE",
                    f"Source as_of {record_as_of} exceeds run as_of {as_of}",
                    str(path),
                    record_id,
                )
            )
        if available_at and available_at > as_of:
            findings.append(
                Finding(
                    "CRITICAL",
                    "FUTURE_AVAILABILITY",
                    f"Evidence became available on {available_at}, after run as_of {as_of}",
                    str(path),
                    record_id,
                )
            )
        if published_at and published_at > as_of:
            findings.append(
                Finding(
                    "CRITICAL",
                    "FUTURE_PUBLICATION",
                    f"Evidence was published on {published_at}, after run as_of {as_of}",
                    str(path),
                    record_id,
                )
            )

        validate_snapshot_hash(
            run_dir,
            record.get("snapshot_path"),
            record.get("content_sha256"),
            findings,
            manifest_path=path,
            record_id=record_id,
            missing_code="MISSING_SNAPSHOT",
        )

        status = record.get("verification_status", "VERIFIED")
        if status not in VERIFICATION_STATUSES:
            findings.append(
                Finding(
                    "CRITICAL",
                    "INVALID_VERIFICATION_STATUS",
                    f"Unknown verification_status: {status}",
                    str(path),
                    record_id,
                )
            )
    return seen


def validate_datasets(run_dir: Path, as_of: dt.date, findings: list[Finding]) -> set[str]:
    path = run_dir / "dataset_manifest.json"
    raw = load_json(path, findings)
    records = records_from_manifest(raw, ("datasets", "records"))
    if raw is not None and not records:
        findings.append(Finding("CRITICAL", "EMPTY_DATASET_MANIFEST", "No dataset records found", str(path)))

    seen: set[str] = set()
    required = (
        "dataset_id",
        "source_ids",
        "raw_path",
        "raw_sha256",
        "row_count",
        "observation_start",
        "observation_end",
        "timezone",
        "frequency",
        "unit",
        "schema_fingerprint",
        "validation_status",
    )
    for record in records:
        record_id = str(record.get("dataset_id") or "<unknown>")
        require_fields(record, required, findings, manifest_path=path, record_id=record_id)
        if record_id != "<unknown>":
            if record_id in seen:
                findings.append(
                    Finding("CRITICAL", "DUPLICATE_DATASET_ID", f"Duplicate dataset ID: {record_id}", str(path), record_id)
                )
            seen.add(record_id)

        start = parse_date(record.get("observation_start"), "observation_start", findings, path=str(path), record_id=record_id)
        end = parse_date(record.get("observation_end"), "observation_end", findings, path=str(path), record_id=record_id)
        max_available = parse_date(record.get("max_available_at"), "max_available_at", findings, path=str(path), record_id=record_id)
        if start and end and start > end:
            findings.append(
                Finding(
                    "CRITICAL",
                    "INVALID_OBSERVATION_RANGE",
                    f"observation_start {start} is after observation_end {end}",
                    str(path),
                    record_id,
                )
            )
        if end and end > as_of:
            findings.append(
                Finding(
                    "CRITICAL",
                    "FUTURE_OBSERVATION",
                    f"observation_end {end} exceeds run as_of {as_of}",
                    str(path),
                    record_id,
                )
            )
        if max_available and max_available > as_of:
            findings.append(
                Finding(
                    "CRITICAL",
                    "FUTURE_AVAILABILITY",
                    f"max_available_at {max_available} exceeds run as_of {as_of}",
                    str(path),
                    record_id,
                )
            )

        row_count = record.get("row_count")
        if not isinstance(row_count, int) or row_count < 0:
            findings.append(
                Finding(
                    "CRITICAL",
                    "INVALID_ROW_COUNT",
                    f"row_count must be a non-negative integer: {row_count!r}",
                    str(path),
                    record_id,
                )
            )

        for field in ("missingness", "duplicate_rate"):
            value = record.get(field)
            if value is not None and (
                not isinstance(value, (int, float))
                or math.isnan(float(value))
                or not 0 <= float(value) <= 1
            ):
                findings.append(
                    Finding("CRITICAL", "INVALID_RATE", f"{field} must be between 0 and 1: {value!r}", str(path), record_id)
                )
        if float(record.get("missingness", 0) or 0) > float(record.get("allowed_missingness", 0.05)):
            findings.append(
                Finding("CRITICAL", "MISSINGNESS_EXCEEDED", "Dataset missingness exceeds allowed threshold", str(path), record_id)
            )
        if float(record.get("duplicate_rate", 0) or 0) > float(record.get("allowed_duplicate_rate", 0)):
            findings.append(
                Finding("CRITICAL", "DUPLICATES_EXCEEDED", "Dataset duplicate rate exceeds allowed threshold", str(path), record_id)
            )

        if record.get("synthetic_or_proxy") and not record.get("proxy_approval"):
            findings.append(
                Finding("CRITICAL", "UNAPPROVED_PROXY", "Synthetic/proxy dataset lacks proxy_approval", str(path), record_id)
            )

        validate_snapshot_hash(
            run_dir,
            record.get("raw_path"),
            record.get("raw_sha256"),
            findings,
            manifest_path=path,
            record_id=record_id,
            missing_code="MISSING_DATASET_SNAPSHOT",
        )

        if record.get("validation_status") != "VALIDATED":
            findings.append(
                Finding(
                    "CRITICAL",
                    "DATASET_NOT_VALIDATED",
                    f"validation_status is {record.get('validation_status')!r}, expected VALIDATED",
                    str(path),
                    record_id,
                )
            )
    return seen


def validate_calculations(run_dir: Path, dataset_ids: set[str], findings: list[Finding]) -> set[str]:
    path = run_dir / "calculation_manifest.json"
    raw = load_json(path, findings)
    records = records_from_manifest(raw, ("calculations", "records"))
    if raw is not None and not records:
        findings.append(Finding("WARNING", "EMPTY_CALCULATION_MANIFEST", "No calculation records found", str(path)))

    seen: set[str] = set()
    for record in records:
        record_id = str(record.get("calculation_id") or "<unknown>")
        require_fields(
            record,
            ("calculation_id", "input_dataset_ids", "code_ref", "parameters", "output_hash"),
            findings,
            manifest_path=path,
            record_id=record_id,
        )
        if record_id != "<unknown>":
            if record_id in seen:
                findings.append(
                    Finding(
                        "CRITICAL",
                        "DUPLICATE_CALCULATION_ID",
                        f"Duplicate calculation ID: {record_id}",
                        str(path),
                        record_id,
                    )
                )
            seen.add(record_id)
        for dataset_id in record.get("input_dataset_ids") or []:
            if dataset_id not in dataset_ids:
                findings.append(
                    Finding(
                        "CRITICAL",
                        "UNKNOWN_DATASET_REFERENCE",
                        f"Calculation references unknown dataset: {dataset_id}",
                        str(path),
                        record_id,
                    )
                )
        output_hash = str(record.get("output_hash") or "")
        if output_hash and not SHA256_RE.fullmatch(output_hash):
            findings.append(
                Finding("CRITICAL", "INVALID_SHA256", "output_hash must be 64 hexadecimal characters", str(path), record_id)
            )
    return seen


def validate_claims(
    run_dir: Path,
    evidence_ids: set[str],
    calculation_ids: set[str],
    as_of: dt.date,
    findings: list[Finding],
) -> dict[str, Any]:
    path = run_dir / "claim_ledger.jsonl"
    records = load_jsonl(path, findings)
    seen: set[str] = set()
    material_count = 0
    covered_material_count = 0

    for record in records:
        record_id = str(record.get("claim_id") or "<unknown>")
        require_fields(
            record,
            ("claim_id", "text", "classification", "material", "status"),
            findings,
            manifest_path=path,
            record_id=record_id,
        )
        if record_id != "<unknown>":
            if record_id in seen:
                findings.append(
                    Finding("CRITICAL", "DUPLICATE_CLAIM_ID", f"Duplicate claim ID: {record_id}", str(path), record_id)
                )
            seen.add(record_id)

        classification = record.get("classification")
        if classification not in CLAIM_CLASSES:
            findings.append(
                Finding("CRITICAL", "INVALID_CLAIM_CLASS", f"Unknown classification: {classification}", str(path), record_id)
            )
        status = record.get("status")
        if status not in VERIFICATION_STATUSES:
            findings.append(
                Finding(
                    "CRITICAL",
                    "INVALID_VERIFICATION_STATUS",
                    f"Unknown claim status: {status}",
                    str(path),
                    record_id,
                )
            )
        claim_as_of = parse_date(record.get("as_of"), "as_of", findings, path=str(path), record_id=record_id)
        if claim_as_of and claim_as_of > as_of:
            findings.append(
                Finding(
                    "CRITICAL",
                    "CLAIM_ASOF_IN_FUTURE",
                    f"Claim as_of {claim_as_of} exceeds run as_of {as_of}",
                    str(path),
                    record_id,
                )
            )

        evidence = set(record.get("evidence_ids") or [])
        calculations = set(record.get("calculation_ids") or [])
        for evidence_id in evidence - evidence_ids:
            findings.append(
                Finding(
                    "CRITICAL",
                    "UNKNOWN_EVIDENCE_REFERENCE",
                    f"Claim references unknown evidence: {evidence_id}",
                    str(path),
                    record_id,
                )
            )
        for calculation_id in calculations - calculation_ids:
            findings.append(
                Finding(
                    "CRITICAL",
                    "UNKNOWN_CALCULATION_REFERENCE",
                    f"Claim references unknown calculation: {calculation_id}",
                    str(path),
                    record_id,
                )
            )

        material = record.get("material") is True
        if material:
            material_count += 1
        if classification == "FACT":
            supported = bool(evidence)
            if material and not supported:
                findings.append(
                    Finding("CRITICAL", "UNSUPPORTED_MATERIAL_FACT", "Material FACT has no evidence_ids", str(path), record_id)
                )
        elif classification == "CALCULATION":
            supported = bool(calculations)
            if material and not supported:
                findings.append(
                    Finding(
                        "CRITICAL",
                        "UNSUPPORTED_MATERIAL_CALCULATION",
                        "Material CALCULATION has no calculation_ids",
                        str(path),
                        record_id,
                    )
                )
        else:
            supported = bool(evidence or calculations)
            if material and not supported:
                findings.append(
                    Finding(
                        "CRITICAL",
                        "UNSUPPORTED_MATERIAL_INTERPRETATION",
                        f"Material {classification} has no support",
                        str(path),
                        record_id,
                    )
                )

        if (
            material
            and supported
            and status == "VERIFIED"
            and record.get("contradiction_status", "NONE") != "UNRESOLVED"
        ):
            covered_material_count += 1
        if material and record.get("contradiction_status") == "UNRESOLVED":
            findings.append(
                Finding(
                    "CRITICAL",
                    "UNRESOLVED_MATERIAL_CONTRADICTION",
                    "Material claim has unresolved contradiction",
                    str(path),
                    record_id,
                )
            )

    coverage = 1.0 if material_count == 0 else covered_material_count / material_count
    if coverage < 1.0:
        findings.append(
            Finding(
                "CRITICAL",
                "INCOMPLETE_MATERIAL_COVERAGE",
                f"Material claim coverage is {coverage:.2%}; required 100%",
                str(path),
            )
        )
    return {
        "claims": len(records),
        "material_claims": material_count,
        "covered_material_claims": covered_material_count,
        "material_coverage": coverage,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate financial research evidence and point-in-time integrity")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--as-of", required=True, help="Run as-of date in YYYY-MM-DD format")
    parser.add_argument(
        "--stage",
        choices=("acquisition", "release"),
        default="release",
        help="acquisition validates source/dataset inputs; release also validates calculations and claims",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional output report path; defaults to <run-dir>/data_gate_report.json",
    )
    args = parser.parse_args()

    try:
        as_of = dt.date.fromisoformat(args.as_of)
    except ValueError:
        print("--as-of must use YYYY-MM-DD", file=sys.stderr)
        return 2

    run_dir = args.run_dir.resolve()
    findings: list[Finding] = []
    if not run_dir.is_dir():
        findings.append(
            Finding("CRITICAL", "MISSING_RUN_DIR", f"Run directory does not exist: {run_dir}", str(run_dir))
        )

    evidence_ids = validate_sources(run_dir, as_of, findings) if run_dir.is_dir() else set()
    dataset_ids = validate_datasets(run_dir, as_of, findings) if run_dir.is_dir() else set()
    calculation_ids: set[str] = set()
    claim_stats: dict[str, Any] = {}
    if run_dir.is_dir() and args.stage == "release":
        calculation_ids = validate_calculations(run_dir, dataset_ids, findings)
        claim_stats = validate_claims(run_dir, evidence_ids, calculation_ids, as_of, findings)

    critical = sum(1 for finding in findings if finding.severity == "CRITICAL")
    warning = sum(1 for finding in findings if finding.severity == "WARNING")
    report = {
        "status": "PASS" if critical == 0 else "FAIL",
        "as_of": as_of.isoformat(),
        "stage": args.stage,
        "run_dir": str(run_dir),
        "summary": {
            "critical_count": critical,
            "warning_count": warning,
            "evidence_records": len(evidence_ids),
            "dataset_records": len(dataset_ids),
            "calculation_records": len(calculation_ids),
            **claim_stats,
        },
        "findings": [asdict(finding) for finding in findings],
        "validator": {"name": "validate_evidence.py", "version": 1},
    }

    report_path = (args.report or (run_dir / "data_gate_report.json")).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if critical == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
