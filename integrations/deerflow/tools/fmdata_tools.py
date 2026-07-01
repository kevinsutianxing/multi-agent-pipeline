"""Restricted official-DeerFlow tools for the fmdata research API.

These tools create or inspect PENDING fmdata snapshots. They do not download
files into a research run, validate financial facts, or write run manifests.
The external controller must independently materialize and verify every request
with ``adapters/fmdata_client.py`` before analysis is allowed.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Literal

from langchain_core.tools import tool

_ALLOWED_DATASET_TYPES = {"market", "fundamental", "macro", "industry"}


class FMDataToolError(RuntimeError):
    pass


def _base_url() -> str:
    return (os.environ.get("FMDATA_URL") or "http://127.0.0.1:1934").rstrip("/")


def _research_key() -> str:
    key = os.environ.get("FMDATA_RESEARCH_KEY") or ""
    if not key:
        raise FMDataToolError("FMDATA_RESEARCH_KEY is not configured")
    return key


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None
    headers = {
        "Accept": "application/json",
        "X-Research-Key": _research_key(),
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        _base_url() + path,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1500]
        raise FMDataToolError(f"fmdata HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise FMDataToolError(f"fmdata unavailable: {exc.reason}") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FMDataToolError(f"fmdata returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise FMDataToolError("fmdata response is not a JSON object")
    return value


def _snapshot_request(
    dataset_type: Literal["market", "fundamental", "macro", "industry"],
    dataset: str,
    as_of: str,
    fields: list[str] | None,
    entity_ids: list[str] | None,
    start_date: str | None,
    end_date: str | None,
    parameters: dict[str, Any] | None,
    expected_semantics: dict[str, Any] | None,
) -> dict[str, Any]:
    if dataset_type not in _ALLOWED_DATASET_TYPES:
        raise FMDataToolError(f"unsupported dataset_type: {dataset_type}")
    payload = {
        "dataset": dataset,
        "as_of": as_of,
        "fields": fields or [],
        "entity_ids": entity_ids or [],
        "start_date": start_date,
        "end_date": end_date,
        "parameters": {
            **(parameters or {}),
            "research_dataset_type": dataset_type,
        },
        "expected_semantics": expected_semantics or {},
    }
    result = _request("POST", "/research/snapshots", payload)
    # The service must remain non-authoritative. Refuse any response claiming
    # final validation, and surface PARTIAL/CONFLICTED rather than hiding it.
    if result.get("validation_status") != "PENDING":
        raise FMDataToolError(
            "fmdata violated the trust contract: expected validation_status=PENDING"
        )
    return {
        "status": result.get("status"),
        "snapshot_id": result.get("snapshot_id"),
        "dataset_id": result.get("dataset_id"),
        "evidence_id": result.get("evidence_id"),
        "provider": result.get("provider"),
        "row_count": result.get("row_count"),
        "observation_start": result.get("observation_start"),
        "observation_end": result.get("observation_end"),
        "manifest_url": result.get("manifest_url"),
        "limitations": result.get("limitations") or [],
        "conflicts": result.get("conflicts") or [],
        "validation_status": "PENDING",
        "required_next_action": (
            "External controller must rerun this exact bounded request with "
            "adapters/fmdata_client.py and pass the acquisition gate."
        ),
    }


@tool
def describe_dataset(dataset: str) -> dict[str, Any]:
    """Return fmdata catalogue metadata and limitations for one registered dataset."""
    catalog = _request("GET", "/research/catalog")
    record = (catalog.get("datasets") or {}).get(dataset)
    if record is None:
        return {"status": "NOT_FOUND", "dataset": dataset}
    return {"status": "OK", "dataset": dataset, "metadata": record}


@tool
def resolve_financial_entity(
    query: str,
    as_of: str,
    expected_name: str | None = None,
    market_hint: str | None = None,
) -> dict[str, Any]:
    """Resolve a security reference without best-guess ambiguity."""
    return _request(
        "POST",
        "/research/entities/resolve",
        {
            "query": query,
            "as_of": as_of,
            "expected_name": expected_name,
            "market_hint": market_hint,
        },
    )


@tool
def fetch_market_data_snapshot(
    dataset: str,
    as_of: str,
    fields: list[str] | None = None,
    entity_ids: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    parameters: dict[str, Any] | None = None,
    expected_semantics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a PENDING immutable market-data snapshot in fmdata."""
    return _snapshot_request(
        "market", dataset, as_of, fields, entity_ids, start_date, end_date,
        parameters, expected_semantics,
    )


@tool
def fetch_fundamental_snapshot(
    dataset: str,
    as_of: str,
    fields: list[str] | None = None,
    entity_ids: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    parameters: dict[str, Any] | None = None,
    expected_semantics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a PENDING immutable fundamental-data snapshot in fmdata."""
    return _snapshot_request(
        "fundamental", dataset, as_of, fields, entity_ids, start_date, end_date,
        parameters, expected_semantics,
    )


@tool
def fetch_macro_snapshot(
    dataset: str,
    as_of: str,
    fields: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    parameters: dict[str, Any] | None = None,
    expected_semantics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a PENDING immutable macro-data snapshot in fmdata."""
    return _snapshot_request(
        "macro", dataset, as_of, fields, None, start_date, end_date,
        parameters, expected_semantics,
    )


@tool
def fetch_industry_dataset_snapshot(
    dataset: str,
    as_of: str,
    fields: list[str] | None = None,
    entity_ids: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    parameters: dict[str, Any] | None = None,
    expected_semantics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a PENDING immutable industry-data snapshot in fmdata."""
    return _snapshot_request(
        "industry", dataset, as_of, fields, entity_ids, start_date, end_date,
        parameters, expected_semantics,
    )
