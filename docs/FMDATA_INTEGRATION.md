# fmdata Integration with the Codex–DeerFlow Research System

## Architecture decision

`kevinsutianxing/fmdata` is the financial data plane. Official ByteDance DeerFlow is the agent execution harness. They are separate trust boundaries.

```text
Codex research plan
        |
        v
Official DeerFlow finance-evidence-agent
        |
        | bounded MCP request
        v
fmdata research snapshot API
        |
        | PENDING snapshot ID + metadata
        v
External fmdata materializer
        |
        | download + hashes + quality + semantics
        v
source/dataset manifest segments
        |
        v
Deterministic acquisition gate
        |
        v
validated data available to analysis agents
```

Neither DeerFlow nor fmdata may promote data to research-valid by assertion.

## fmdata service requirement

The deployed service must include the research snapshot API from:

```text
kevinsutianxing/fmdata
branch: feat/research-snapshot-api
PR: https://github.com/kevinsutianxing/fmdata/pull/1
```

Required environment:

```bash
FMDATA_URL=http://127.0.0.1:1934
FMDATA_RESEARCH_KEY=<research-only-secret>
FMDATA_SNAPSHOT_DIR=/immutable/fmdata-snapshots
```

The snapshot directory should use append-only or equivalent protected storage. Research agents must not receive filesystem write authority over it.

## 1. Preflight

Create a dataset-requirements file from the approved Codex plan:

```json
{
  "datasets": [
    {
      "dataset": "daily_basic",
      "research_ready": true,
      "expected_semantics": {
        "frequency": "daily",
        "currency": "CNY"
      }
    }
  ]
}
```

Run:

```bash
python scripts/fmdata_preflight.py \
  --base-url "$FMDATA_URL" \
  --requirements runs/$RUN_ID/fmdata_requirements.json \
  --report runs/$RUN_ID/fmdata_preflight_report.json
```

Preflight checks the API contract, authentication, self-validation policy, catalogue presence, row availability, research-ready status, and expected semantics. It does not prove that a requested snapshot is correct.

## 2. DeerFlow MCP configuration

Mount this repository into the official DeerFlow environment and register:

```text
integrations/deerflow/extensions_config.finance-research.example.json
integrations/deerflow/fmdata_mcp_server.py
integrations/deerflow/tools/fmdata_tools.py
```

The MCP server currently exposes only implemented capabilities:

- `describe_dataset`
- `resolve_financial_entity`
- `fetch_market_data_snapshot`
- `fetch_fundamental_snapshot`
- `fetch_macro_snapshot`
- `fetch_industry_dataset_snapshot`

There is intentionally no filing-snapshot, revision-listing, or web-evidence-snapshot tool yet. Agents must not claim those capabilities exist.

## 3. Bounded snapshot request

Codex creates an immutable request file such as:

```json
{
  "dataset": "daily_basic",
  "as_of": "2026-06-30",
  "start_date": "2026-06-01",
  "end_date": "2026-06-30",
  "entity_ids": ["000001.SZ"],
  "fields": ["pe_ttm", "pb", "total_mv"],
  "parameters": {},
  "expected_semantics": {
    "frequency": "daily",
    "currency": "CNY"
  }
}
```

DeerFlow may call the matching MCP tool to discover whether fmdata can create the snapshot. The result remains `PENDING` and is not sufficient to enter analysis.

## 4. External materialization

The external controller independently reruns the same approved request:

```bash
python adapters/fmdata_client.py snapshot \
  --base-url "$FMDATA_URL" \
  --run-dir runs/$RUN_ID \
  --task-id market-daily-basic \
  --request-file runs/$RUN_ID/tasks/market-daily-basic/fmdata_request.json
```

The adapter:

1. stores a redacted request and fmdata response;
2. fetches the service-generated manifest;
3. verifies response/manifest identity;
4. requires `validation_status=PENDING` from fmdata;
5. rejects `PARTIAL`, `CONFLICTED`, and `ERROR` snapshots;
6. downloads raw and normalized objects;
7. verifies both SHA-256 hashes;
8. parses the normalized CSV;
9. reconciles row count;
10. measures missingness and duplicate rate;
11. requires core semantic fields;
12. writes run-local immutable copies;
13. emits source and dataset manifest segments.

Example outputs:

```text
runs/<run_id>/fmdata/<task_id>/request.json
runs/<run_id>/fmdata/<task_id>/response.json
runs/<run_id>/fmdata/<task_id>/manifest.json
runs/<run_id>/fmdata/<task_id>/materialization.json
runs/<run_id>/raw/fmdata/...
runs/<run_id>/source_manifest.fmdata.<task_id>.json
runs/<run_id>/dataset_manifest.fmdata.<task_id>.json
```

## 5. Deterministic merge and gate

After all data and evidence workers finish:

```bash
python scripts/merge_manifests.py --run-dir runs/$RUN_ID
python scripts/validate_evidence.py \
  --run-dir runs/$RUN_ID \
  --as-of YYYY-MM-DD \
  --stage acquisition \
  --report runs/$RUN_ID/acquisition_gate_report.json
```

`merge_manifests.py` merges source and dataset segments and rejects conflicting duplicate IDs. `validate_evidence.py` independently checks run-local hashes, time boundaries, quality thresholds, semantics, and validation status.

Only a passing acquisition gate allows quantitative or industry analysis.

## Trust rules

- fmdata cache data is mutable operational storage; a research run references immutable snapshots.
- fmdata returns `PENDING`; only the external adapter and gate produce run-local `VALIDATED` records.
- DeerFlow event logs are operational evidence, not financial-source evidence.
- An Agent-provided DataFrame, prose summary, row preview, or `success=true` is never sufficient.
- Missing point-in-time availability, adjustment, accounting, vintage, unit, or licensing semantics must remain visible and block material use.
- Stock-code validation is necessary but not a substitute for historical entity resolution.
- Existing fmdata recipes are not automatically research-ready merely because they fetch successfully.

## Current validation status

Automated contract tests cover:

- fmdata immutable snapshot IDs and hashes;
- request redaction and path confinement;
- missing semantics and future availability;
- fail-closed research API authentication;
- external download and hash verification;
- quality checks and manifest generation;
- rejection of non-OK service snapshots;
- stable dataset manifest merging and duplicate conflict blocking;
- fmdata preflight contract and semantic requirements.

Still required before production release:

1. deploy the fmdata PR on the real data host;
2. configure a real research-only key and protected snapshot directory;
3. add verified semantics to selected recipes;
4. run one real market snapshot, one fundamental snapshot, and one macro-vintage snapshot;
5. test historical/delisted entity resolution and index constituents;
6. test provider outage, pagination, rate limits, and licensing constraints;
7. run a complete quantitative and industry research project end to end;
8. obtain external Claude Code adversarial review.
