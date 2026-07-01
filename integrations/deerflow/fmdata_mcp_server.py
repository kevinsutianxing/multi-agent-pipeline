"""MCP server exposing the restricted fmdata research snapshot contract.

Run inside the official DeerFlow environment:

    python -m integrations.deerflow.fmdata_mcp_server

The server returns PENDING snapshot IDs and metadata only. It never validates a
snapshot or writes the multi-agent run manifests.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from integrations.deerflow.tools.fmdata_tools import _request, _snapshot_request

server = FastMCP("fmdata-research")


@server.tool()
def describe_dataset(dataset: str) -> dict[str, Any]:
    """Describe one registered fmdata dataset and its research limitations."""
    catalog = _request("GET", "/research/catalog")
    record = (catalog.get("datasets") or {}).get(dataset)
    if record is None:
        return {"status": "NOT_FOUND", "dataset": dataset}
    return {"status": "OK", "dataset": dataset, "metadata": record}


@server.tool()
def resolve_financial_entity(
    query: str,
    as_of: str,
    expected_name: str | None = None,
    market_hint: str | None = None,
) -> dict[str, Any]:
    """Resolve an entity without best-guess ambiguity."""
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


@server.tool()
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
    """Create a PENDING immutable market-data snapshot."""
    return _snapshot_request(
        "market", dataset, as_of, fields, entity_ids, start_date, end_date,
        parameters, expected_semantics,
    )


@server.tool()
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
    """Create a PENDING immutable fundamental-data snapshot."""
    return _snapshot_request(
        "fundamental", dataset, as_of, fields, entity_ids, start_date, end_date,
        parameters, expected_semantics,
    )


@server.tool()
def fetch_macro_snapshot(
    dataset: str,
    as_of: str,
    fields: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    parameters: dict[str, Any] | None = None,
    expected_semantics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a PENDING immutable macro-data snapshot."""
    return _snapshot_request(
        "macro", dataset, as_of, fields, None, start_date, end_date,
        parameters, expected_semantics,
    )


@server.tool()
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
    """Create a PENDING immutable industry-data snapshot."""
    return _snapshot_request(
        "industry", dataset, as_of, fields, entity_ids, start_date, end_date,
        parameters, expected_semantics,
    )


if __name__ == "__main__":
    server.run()
