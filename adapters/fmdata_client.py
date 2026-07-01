#!/usr/bin/env python3
"""Narrow client and materializer for the fmdata research snapshot API.

The fmdata service preserves a PENDING immutable snapshot. This adapter is run
by the external controller, not by the research agent. It downloads the exact
snapshot, verifies hashes and basic quality, and writes run-local source and
dataset manifest segments for the deterministic acquisition gate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SECRET_RE = re.compile(
    r"(token|secret|password|passwd|pwd|auth|api[_-]?key|cookie)", re.IGNORECASE
)
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_REQUIRED_SNAPSHOT_FIELDS = {
    "status",
    "snapshot_id",
    "source_id",
    "evidence_id",
    "dataset_id",
    "provider",
    "query_parameters",
    "retrieved_at",
    "as_of",
    "snapshot_path",
    "content_sha256",
    "raw_snapshot_path",
    "raw_content_sha256",
    "row_count",
    "schema_fingerprint",
    "validation_status",
}


class FMDataError(RuntimeError):
    """A transport, contract, or integrity failure."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***REDACTED***" if _SECRET_RE.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def write_json(path: Path, value: Any) -> None:
    atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def safe_id(value: str) -> str:
    cleaned = _SAFE_ID_RE.sub("-", value).strip("-.")
    if not cleaned:
        raise FMDataError("identifier becomes empty after sanitization")
    return cleaned[:160]


@dataclass
class CSVQuality:
    rows: int
    columns: list[str]
    missingness: float
    duplicate_rate: float


def inspect_csv(data: bytes) -> CSVQuality:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FMDataError(f"snapshot CSV is not UTF-8: {exc}") from exc

    reader = csv.reader(text.splitlines())
    try:
        header = next(reader)
    except StopIteration:
        return CSVQuality(rows=0, columns=[], missingness=1.0, duplicate_rate=0.0)

    if not header or any(not column for column in header):
        raise FMDataError("snapshot CSV has an empty header field")
    if len(set(header)) != len(header):
        raise FMDataError("snapshot CSV has duplicate column names")

    rows = 0
    missing = 0
    cells = 0
    duplicates = 0
    seen: set[tuple[str, ...]] = set()
    for row in reader:
        if len(row) != len(header):
            raise FMDataError(
                f"snapshot CSV row {rows + 2} has {len(row)} fields; expected {len(header)}"
            )
        rows += 1
        key = tuple(row)
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
        for value in row:
            cells += 1
            if value.strip() == "" or value.strip().lower() in {"nan", "none", "null"}:
                missing += 1

    return CSVQuality(
        rows=rows,
        columns=header,
        missingness=0.0 if cells == 0 else missing / cells,
        duplicate_rate=0.0 if rows == 0 else duplicates / rows,
    )


class FMDataClient:
    def __init__(
        self,
        base_url: str | None = None,
        research_key: str | None = None,
        timeout: int = 60,
    ) -> None:
        self.base_url = (base_url or os.environ.get("FMDATA_URL") or "http://127.0.0.1:1934").rstrip("/")
        self.research_key = research_key or os.environ.get("FMDATA_RESEARCH_KEY") or ""
        self.timeout = timeout

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + path

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if self.research_key:
            headers["X-Research-Key"] = self.research_key
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            self._url(path),
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            diagnostic = exc.read().decode("utf-8", errors="replace")[:2000]
            raise FMDataError(f"fmdata HTTP {exc.code} for {path}: {diagnostic}") from exc
        except urllib.error.URLError as exc:
            raise FMDataError(f"fmdata transport failure for {path}: {exc.reason}") from exc

        if not expect_json:
            return body
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FMDataError(f"fmdata returned invalid JSON for {path}: {exc}") from exc
        return value

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/research/health")

    def catalog(self) -> dict[str, Any]:
        return self._request("GET", "/research/catalog")

    def resolve_entity(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/research/entities/resolve", payload=payload)

    def create_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/research/snapshots", payload=payload)

    def get_manifest(self, snapshot_id: str) -> dict[str, Any]:
        return self._request("GET", f"/research/snapshots/{urllib.parse.quote(snapshot_id)}/manifest")

    def download_snapshot(self, snapshot_id: str, *, raw: bool = False) -> bytes:
        suffix = "raw" if raw else "data"
        return self._request(
            "GET",
            f"/research/snapshots/{urllib.parse.quote(snapshot_id)}/{suffix}",
            expect_json=False,
        )


def validate_snapshot_contract(manifest: dict[str, Any]) -> None:
    missing = sorted(field for field in _REQUIRED_SNAPSHOT_FIELDS if manifest.get(field) in (None, ""))
    if missing:
        raise FMDataError(f"fmdata snapshot manifest is missing fields: {missing}")
    for field in ("content_sha256", "raw_content_sha256"):
        value = str(manifest[field])
        if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            raise FMDataError(f"{field} is not a SHA-256 digest")
    if manifest.get("validation_status") != "PENDING":
        raise FMDataError(
            "fmdata must return validation_status=PENDING; only the external gate may validate"
        )


def _relative_to_run(run_dir: Path, path: Path) -> str:
    return str(path.resolve().relative_to(run_dir.resolve()))


def materialize_snapshot(
    client: FMDataClient,
    *,
    run_dir: Path,
    task_id: str,
    request_payload: dict[str, Any],
    allowed_missingness: float = 0.05,
    allowed_duplicate_rate: float = 0.0,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    task_slug = safe_id(task_id)
    audit_dir = run_dir / "fmdata" / task_slug
    audit_dir.mkdir(parents=True, exist_ok=True)
    write_json(audit_dir / "request.json", redact(request_payload))

    response = client.create_snapshot(request_payload)
    write_json(audit_dir / "response.json", response)
    validate_snapshot_contract(response)

    snapshot_id = str(response["snapshot_id"])
    manifest = client.get_manifest(snapshot_id)
    write_json(audit_dir / "manifest.json", manifest)
    validate_snapshot_contract(manifest)

    identity_fields = (
        "snapshot_id",
        "source_id",
        "dataset_id",
        "content_sha256",
        "raw_content_sha256",
        "request_sha256",
    )
    for field in identity_fields:
        if response.get(field) != manifest.get(field):
            raise FMDataError(f"response/manifest identity mismatch for {field}")

    if manifest.get("status") != "OK":
        raise FMDataError(
            f"fmdata snapshot is not research-ready: status={manifest.get('status')}; "
            f"limitations={manifest.get('limitations')}; conflicts={manifest.get('conflicts')}"
        )

    normalized = client.download_snapshot(snapshot_id, raw=False)
    raw = client.download_snapshot(snapshot_id, raw=True)
    if sha256_bytes(normalized) != manifest["content_sha256"]:
        raise FMDataError("normalized fmdata snapshot hash mismatch")
    if sha256_bytes(raw) != manifest["raw_content_sha256"]:
        raise FMDataError("raw fmdata snapshot hash mismatch")

    quality = inspect_csv(normalized)
    if quality.rows != int(manifest["row_count"]):
        raise FMDataError(
            f"row-count mismatch: manifest={manifest['row_count']} downloaded={quality.rows}"
        )
    if quality.missingness > allowed_missingness:
        raise FMDataError(
            f"missingness {quality.missingness:.2%} exceeds {allowed_missingness:.2%}"
        )
    if quality.duplicate_rate > allowed_duplicate_rate:
        raise FMDataError(
            f"duplicate rate {quality.duplicate_rate:.2%} exceeds {allowed_duplicate_rate:.2%}"
        )

    required_semantics = ("timezone", "frequency", "unit", "revision_policy")
    missing_semantics = [field for field in required_semantics if not manifest.get(field)]
    if missing_semantics:
        raise FMDataError(f"research snapshot lacks required semantics: {missing_semantics}")

    normalized_target = run_dir / "raw" / "fmdata" / f"{safe_id(snapshot_id)}.csv"
    raw_suffix = Path(str(manifest.get("raw_snapshot_path") or "raw.bin")).suffix or ".bin"
    raw_target = run_dir / "raw" / "fmdata" / f"{safe_id(snapshot_id)}.source{raw_suffix}"
    atomic_write(normalized_target, normalized)
    atomic_write(raw_target, raw)

    source_record = {
        "evidence_id": manifest["evidence_id"],
        "source_id": manifest["source_id"],
        "provider": manifest["provider"],
        "locator": manifest.get("source_locator") or f"fmdata://snapshot/{snapshot_id}",
        "request_parameters": manifest.get("query_parameters") or {},
        "retrieved_at": manifest["retrieved_at"],
        "as_of": manifest["as_of"],
        "published_at": manifest.get("published_at"),
        "available_at": manifest.get("available_at"),
        "available_at_rule": manifest.get("available_at_rule"),
        "snapshot_path": _relative_to_run(run_dir, normalized_target),
        "content_sha256": manifest["content_sha256"],
        "raw_snapshot_path": _relative_to_run(run_dir, raw_target),
        "raw_content_sha256": manifest["raw_content_sha256"],
        "source_tier": "LICENSED_VENDOR",
        "verification_status": "VERIFIED",
        "fmdata_snapshot_id": snapshot_id,
        "limitations": manifest.get("limitations") or [],
    }

    dataset_record = {
        "dataset_id": manifest["dataset_id"],
        "source_ids": [manifest["source_id"]],
        "raw_path": _relative_to_run(run_dir, normalized_target),
        "raw_sha256": manifest["content_sha256"],
        "provider_raw_path": _relative_to_run(run_dir, raw_target),
        "provider_raw_sha256": manifest["raw_content_sha256"],
        "row_count": quality.rows,
        "observation_start": manifest.get("observation_start"),
        "observation_end": manifest.get("observation_end"),
        "max_available_at": manifest.get("available_at"),
        "available_at_rule": manifest.get("available_at_rule"),
        "timezone": manifest["timezone"],
        "frequency": manifest["frequency"],
        "unit": manifest["unit"],
        "currency": manifest.get("currency"),
        "adjustment": manifest.get("adjustment"),
        "revision_policy": manifest["revision_policy"],
        "schema_fingerprint": manifest["schema_fingerprint"],
        "columns": quality.columns,
        "missingness": quality.missingness,
        "duplicate_rate": quality.duplicate_rate,
        "allowed_missingness": allowed_missingness,
        "allowed_duplicate_rate": allowed_duplicate_rate,
        "validation_status": "VALIDATED",
        "synthetic_or_proxy": False,
        "lineage": {
            "service": "fmdata",
            "snapshot_id": snapshot_id,
            "request_sha256": manifest.get("request_sha256"),
            "recipe_sha256": manifest.get("recipe_sha256"),
            "service_validation_status": manifest.get("validation_status"),
        },
    }

    source_segment = run_dir / f"source_manifest.fmdata.{task_slug}.json"
    dataset_segment = run_dir / f"dataset_manifest.fmdata.{task_slug}.json"
    write_json(source_segment, {"version": 1, "sources": [source_record]})
    write_json(dataset_segment, {"version": 1, "datasets": [dataset_record]})

    result = {
        "status": "MATERIALIZED",
        "task_id": task_id,
        "snapshot_id": snapshot_id,
        "source_manifest_segment": _relative_to_run(run_dir, source_segment),
        "dataset_manifest_segment": _relative_to_run(run_dir, dataset_segment),
        "normalized_snapshot": _relative_to_run(run_dir, normalized_target),
        "raw_snapshot": _relative_to_run(run_dir, raw_target),
        "quality": {
            "rows": quality.rows,
            "columns": quality.columns,
            "missingness": quality.missingness,
            "duplicate_rate": quality.duplicate_rate,
        },
    }
    write_json(audit_dir / "materialization.json", result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Use the fmdata research snapshot API")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--timeout", type=int, default=60)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health")
    sub.add_parser("catalog")

    resolve = sub.add_parser("resolve")
    resolve.add_argument("--query", required=True)
    resolve.add_argument("--as-of", required=True)
    resolve.add_argument("--expected-name")
    resolve.add_argument("--market-hint")

    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--run-dir", required=True, type=Path)
    snapshot.add_argument("--task-id", required=True)
    snapshot.add_argument("--request-file", required=True, type=Path)
    snapshot.add_argument("--allowed-missingness", type=float, default=0.05)
    snapshot.add_argument("--allowed-duplicate-rate", type=float, default=0.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    client = FMDataClient(base_url=args.base_url, timeout=args.timeout)
    try:
        if args.command == "health":
            result = client.health()
        elif args.command == "catalog":
            result = client.catalog()
        elif args.command == "resolve":
            result = client.resolve_entity(
                {
                    "query": args.query,
                    "as_of": args.as_of,
                    "expected_name": args.expected_name,
                    "market_hint": args.market_hint,
                }
            )
        else:
            payload = json.loads(args.request_file.read_text(encoding="utf-8"))
            result = materialize_snapshot(
                client,
                run_dir=args.run_dir,
                task_id=args.task_id,
                request_payload=payload,
                allowed_missingness=args.allowed_missingness,
                allowed_duplicate_rate=args.allowed_duplicate_rate,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (FMDataError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
