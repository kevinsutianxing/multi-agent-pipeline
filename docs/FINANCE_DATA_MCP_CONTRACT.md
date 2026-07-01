# Financial Data MCP Contract

## Scope

This contract connects the user's custom financial-data service to the official ByteDance DeerFlow 2.x agent harness.

The two systems are distinct:

- **Official DeerFlow** executes research agents and calls tools.
- **Custom financial-data service** retrieves market, fundamental, macro, filing, and industry data.

The MCP adapter is a narrow data-plane boundary. It must not contain research conclusions, portfolio decisions, or release authority.

## Core invariant

Every material data call must follow:

```text
bounded request
  -> provider request
  -> immutable raw response snapshot
  -> normalized dataset snapshot
  -> metadata and lineage record
  -> PENDING validation result
  -> deterministic acquisition gate
```

A tool response that only returns rows, prose, a dataframe preview, or a success flag is not sufficient.

## Transport

The preferred integration is an MCP server registered in official DeerFlow's `extensions_config.json`.

The concrete implementation may use stdio, HTTP/SSE, or a Python tool wrapper, but it must preserve the same request and response contracts. Authentication secrets must remain in process environment or a secret manager and must never be copied into research manifests.

## Required operational properties

### Idempotency

Every retrieval request must accept or derive a stable `request_id`. Repeating an identical request should return the same snapshot IDs when the underlying provider response is unchanged, or create a new revision linked to the previous snapshot when it changes.

### Snapshot-first storage

Raw provider responses must be persisted before normalization. Recommended layout:

```text
content_store/
  raw/<sha256>
  normalized/<sha256>
  metadata/<dataset_id>.json
```

Research runs should reference content-addressed immutable snapshots. When files are copied into `runs/<run_id>/raw/`, their hashes must remain identical.

### Point-in-time semantics

The adapter must distinguish:

- `observation_start` / `observation_end`: period described by the data;
- `published_at`: first public release timestamp;
- `available_at`: earliest time the data was available through the selected source;
- `retrieved_at`: time this system fetched the data;
- `as_of`: latest information time permitted by the research task;
- `revision_policy`: whether the returned value is original, revised, restated, or latest-known.

Historical research must reject or explicitly label any record with `available_at > as_of`.

### Entity identity

The service must not rely on ticker strings alone. Entity-resolution results should include, when available:

- stable internal entity ID;
- exchange and market;
- security type;
- local ticker and vendor identifiers;
- legal entity ID or issuer relationship;
- effective date range;
- symbol-change, merger, delisting, and corporate-action history;
- mapping confidence and source evidence.

Ambiguous mappings must return `CONFLICTED` or `NOT_FOUND`, not the most likely guess.

### Units and accounting meaning

Every numeric field must carry enough metadata to prevent silent semantic errors:

- unit and scale;
- currency and FX treatment;
- timezone and market calendar;
- frequency;
- raw, split-adjusted, dividend-adjusted, or total-return convention;
- cumulative versus single-period financial statement value;
- consolidated versus parent-only scope;
- GAAP/accounting standard and restatement status where relevant.

## Required response schema

All snapshot-producing tools return an object conforming to:

```text
schemas/finance-data-snapshot.schema.json
```

The service must return `validation_status: PENDING`. Only the external deterministic gate may promote a dataset to `VALIDATED`.

## Recommended MCP tools

These are logical tool contracts. Exact server-side function names may differ only if the mapping is documented and tested.

### `resolve_financial_entity`

Purpose: resolve a user or plan-supplied entity reference into stable point-in-time identifiers.

Required request fields:

```json
{
  "request_id": "string",
  "query": "string",
  "as_of": "YYYY-MM-DD",
  "market_hint": null,
  "security_type_hint": null
}
```

Required result additions:

```json
{
  "status": "OK | CONFLICTED | NOT_FOUND | ERROR",
  "entity_id": "string-or-null",
  "identifiers": {},
  "effective_start": "YYYY-MM-DD-or-null",
  "effective_end": "YYYY-MM-DD-or-null",
  "mapping_confidence": 0.0,
  "mapping_evidence_ids": []
}
```

### `fetch_market_data_snapshot`

Purpose: retrieve price, volume, return, corporate-action, constituent, or market-microstructure data.

The request must specify:

- stable entity/security IDs;
- fields;
- observation window;
- requested frequency;
- timezone/calendar;
- adjustment convention;
- requested as-of date;
- revision/latest policy.

The response must not silently change frequency, adjustment, calendar, or field definitions.

### `fetch_fundamental_snapshot`

Purpose: retrieve financial statements, estimates, ownership, segment, or issuer fundamentals.

The request must specify:

- issuer/entity IDs;
- statement type and fields;
- fiscal period or filing window;
- consolidated/parent scope;
- accounting standard where material;
- original versus restated values;
- as-of date.

The response must distinguish period end, announcement/filing date, and source availability date.

### `fetch_macro_snapshot`

Purpose: retrieve official macroeconomic or policy series.

The response must include release vintage/revision information. A latest revised series may not be used in a historical point-in-time analysis unless the research plan explicitly permits it.

### `fetch_filing_snapshot`

Purpose: retrieve an immutable filing or official disclosure plus metadata.

The response should include issuer, filing type, filing/announcement timestamp, reporting period, source locator, document snapshot, and content hash.

### `fetch_industry_dataset_snapshot`

Purpose: retrieve shipment, capacity, utilization, inventory, price, order, policy, market-share, or other industry datasets.

The response must state taxonomy, geographic scope, entity coverage, units, methodology, publication frequency, and known revisions or breaks in series.

### `describe_dataset`

Purpose: return field dictionary, provider lineage, methodology, units, revisions, coverage, limitations, and licensing without retrieving the full dataset.

### `list_data_revisions`

Purpose: enumerate revisions/restatements/vintages for a source series or dataset so the planner can select a point-in-time-safe version.

### `capture_web_evidence_snapshot`

Purpose: preserve a web page or official web document discovered by the industry research agent.

This tool must capture the content, retrieval timestamp, source locator, content hash, publication/availability metadata when known, and a verification status. It must not accept a search-result snippet as the snapshot.

## Error contract

Tools should return structured terminal states rather than plausible partial values:

| Status | Meaning | Research behavior |
|---|---|---|
| `OK` | Retrieval completed and snapshot preserved | Send to acquisition gate |
| `PARTIAL` | Some requested coverage is missing | Preserve; gate evaluates fitness |
| `NOT_FOUND` | No matching source/entity/data | Stop or use an approved alternative |
| `CONFLICTED` | Multiple incompatible mappings or values | Preserve all alternatives; block material use |
| `ERROR` | Transport/provider/internal failure | Retry within policy or return `BLOCKED_EXTERNAL` |

The service must expose retryability, provider error code, and a redacted diagnostic message. It must never convert an error into zero, null-filled rows, or an estimated value without explicit proxy approval.

## Pagination and completeness

For paginated providers, the adapter must record:

- page/cursor sequence;
- expected versus received page count when known;
- per-page hashes or one canonical aggregate hash;
- truncation indicators;
- provider limits;
- row-count reconciliation.

A successful first page is not a complete dataset.

## Rate limits and retries

- Use bounded exponential backoff with jitter.
- Record attempt count and provider response codes.
- Respect provider rate-limit headers.
- Do not retry validation or semantic errors as transport errors.
- Do not exceed the research run's maximum automated attempts.
- Return `BLOCKED_EXTERNAL` after the retry policy is exhausted.

## Security and licensing

- Redact API keys, cookies, tokens, and signed URLs from manifests and logs.
- Keep provider credentials outside the DeerFlow prompt and workspace.
- Restrict tools to read-only retrieval operations.
- Do not expose arbitrary SQL, arbitrary URL fetch, or arbitrary filesystem paths through the financial MCP server.
- Record provider licensing, storage, redistribution, and derived-work restrictions.
- Prevent the agent from copying restricted raw datasets into final deliverables.

## Acceptance tests required before production

The custom financial-data service is not production-ready until tests cover at least:

1. entity resolution with ticker changes and ambiguous names;
2. adjusted versus unadjusted market prices;
3. delisted securities and historical index constituents;
4. original versus revised macro vintages;
5. cumulative versus single-quarter financial statement values;
6. filing period end versus publication date;
7. unit/currency/scale conversion metadata;
8. pagination completeness;
9. provider outage, rate limit, and retry exhaustion;
10. immutable snapshot and hash reproducibility;
11. conflicting cross-source values;
12. licensing metadata;
13. future-information rejection for a historical as-of date.

Each fixture must include the expected manifest and deterministic gate result.

## Separation from agent output

The official DeerFlow agent may request data and organize returned IDs, but it may not write or overwrite service-generated source metadata. The service creates source/dataset records; the deterministic merger and validator consume them; the agent only references them.
