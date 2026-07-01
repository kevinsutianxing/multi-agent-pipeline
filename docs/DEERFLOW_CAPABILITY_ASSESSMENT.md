# DeerFlow Capability Assessment and Architecture Decision

**Assessment date:** 2026-07-01  
**Official project assessed:** `bytedance/deer-flow`, DeerFlow 2.x `main`

## Executive decision

The system contains two different things that happen to share the DeerFlow name:

1. **Official ByteDance DeerFlow 2.x** — a LangGraph/LangChain super-agent harness with custom agents, subagents, skills, MCP tools, sandbox execution, memory, Gateway APIs, and ACP delegation.
2. **The user's custom DeerFlow financial-data service** — a separate data service whose transport and dataset catalogue are not yet documented in this repository.

They must not be modeled as one component.

The chosen architecture is:

```text
Codex external chief planner and integrator
                    |
                    v
         deterministic run controller
                    |
           official DeerFlow Gateway
       /              |                \
finance-evidence  industry-research  quant-analysis
 custom agent       custom agent      custom agent
       \              |                /
                    MCP
                    |
       custom DeerFlow financial-data service
                    |
       immutable snapshots + metadata + hashes
```

Official DeerFlow is an **execution and delegation runtime**. The custom financial-data service is the **data plane**. Codex remains the research control-plane planner. Deterministic scripts and an independent reviewer remain the release authority.

## What DeerFlow 2.x is good at

### 1. Long-horizon execution

DeerFlow provides a Lead Agent, thread persistence, planning mode, subagent delegation, configurable recursion limits, token budgets, loop detection, and recovery for interrupted tool-call sequences. This makes it suitable for multi-step research collection and artifact production.

### 2. Scoped parallel workers

Built-in and custom subagents have isolated contexts and can execute in parallel. Custom agents can be restricted by model, skill whitelist, and tool-group whitelist. This is a good match for separate financial evidence, industry research, and quantitative analysis roles.

### 3. External agent delegation

DeerFlow supports Agent Connect Protocol agents, including Codex and Claude Code through compatible ACP adapters. This is useful for bounded implementation and debugging tasks.

ACP should not be used to create fake reviewer independence. A Claude Code process spawned by the same DeerFlow execution may be useful as a critic, but the final release reviewer should run through a separately controlled review task with its own identity and report artifact.

### 4. Extensible data/tool access

MCP tools, Python tools, and community search/fetch tools can be added without modifying the harness. This is the correct extension point for the custom financial-data service.

### 5. Sandbox and artifact production

DeerFlow can use local, container, cloud, or Kubernetes sandboxes and gives each thread a workspace, uploads directory, and outputs directory. It can execute code, process datasets, generate charts, and preserve artifacts.

### 6. Observability

The Gateway records thread/run identities and can stream detailed events. DeerFlow also supports LangSmith and Langfuse tracing, including session, user, assistant, model, and environment correlation.

Tracing is operational evidence, not financial source evidence. Research runs must still preserve source snapshots, query parameters, hashes, calculation lineage, and claim mappings.

## What DeerFlow 2.x does not guarantee

### 1. Financial source correctness

DeerFlow does not know whether a price is adjusted correctly, whether a financial statement value is cumulative or single-quarter, whether an index constituent list is point-in-time, or whether a macro series has been revised.

Those guarantees belong in the custom financial-data service and deterministic validation layer.

### 2. Citation truth

A deep-research agent can find and summarize sources, but its prose is not proof that a source exists or supports a claim. Source retrieval must produce preserved snapshots and stable evidence IDs.

### 3. Reviewer independence

Subagents and ACP agents are managed by the DeerFlow parent process. They provide context separation, not organizational or release independence.

### 4. Safe autonomous skill evolution

DeerFlow can autonomously create or improve skills. This is inappropriate for production financial research because one run could silently alter future methodology. Skill evolution must remain disabled. Approved skills must be versioned in Git and mounted read-only.

### 5. Research-safe memory by default

DeerFlow memory extracts facts and summaries from conversations and injects them into future prompts. This is useful for user preferences and workflow context, but it can contaminate point-in-time research with stale or unsupported facts.

Production research agents should use a dedicated DeerFlow profile with memory injection disabled. Approved operational knowledge belongs in versioned skills or controlled memory, never in the evidence chain.

## Role design inside official DeerFlow

### `finance-evidence-agent`

Purpose:

- execute bounded requests against financial-data MCP tools;
- collect filings and official-source evidence;
- return stable evidence and dataset IDs;
- report gaps and conflicts.

Restrictions:

- no investment conclusions;
- no self-validation;
- no silent symbol mapping, backfill, proxy substitution, or unit conversion;
- no untracked web values in material claims;
- no unrestricted shell access.

### `industry-research-agent`

Purpose:

- map value chains, entities, competitors, regulation, supply/demand, capacity, pricing, inventory, utilization, and industry KPIs;
- gather primary and reputable secondary evidence;
- identify contradictory sources and missing evidence.

Restrictions:

- web search/fetch is evidence discovery, not source acceptance;
- material facts must resolve to snapshot-backed evidence IDs;
- no direct access to portfolio or recommendation tools.

### `quant-analysis-agent`

Purpose:

- read only datasets that passed the acquisition gate;
- run reproducible calculations in an isolated sandbox;
- produce calculation manifests, diagnostics, charts, and claim candidates.

Restrictions:

- no live web search or unvalidated data tools;
- no modification of raw snapshots;
- no changing methodology after seeing results;
- no final release decision.

## Financial-data MCP design

The custom DeerFlow financial-data service should be exposed to official DeerFlow through a narrow MCP server or equivalent Python tool adapter.

The MCP layer must be snapshot-first. A tool call should not merely return rows. It should return or create:

```json
{
  "status": "OK",
  "source_id": "src-...",
  "evidence_id": "ev-...",
  "dataset_id": "ds-...",
  "provider": "provider-name",
  "query_parameters": {},
  "retrieved_at": "ISO-8601",
  "as_of": "YYYY-MM-DD",
  "published_at": null,
  "available_at": null,
  "snapshot_path": "content-addressed-or-run-relative-path",
  "content_sha256": "64-hex",
  "unit": "...",
  "currency": "...",
  "timezone": "...",
  "frequency": "...",
  "adjustment": "...",
  "validation_status": "PENDING"
}
```

Recommended initial tools:

- `resolve_financial_entity`
- `fetch_market_data_snapshot`
- `fetch_fundamental_snapshot`
- `fetch_macro_snapshot`
- `fetch_filing_snapshot`
- `fetch_industry_dataset_snapshot`
- `describe_dataset`
- `list_data_revisions`

The adapter should preserve raw provider responses before normalization. The agent should receive IDs and controlled previews; it should not be responsible for inventing manifest metadata.

## Production DeerFlow profile

### Memory

```yaml
memory:
  enabled: true
  injection_enabled: false
```

Memory storage may remain enabled for operational review, but research custom agents should not receive extracted memory facts in their prompt.

### Skill evolution

```yaml
skill_evolution:
  enabled: false
```

### Tool search

```yaml
tool_search:
  enabled: true
```

This is recommended when financial MCP servers expose many tools. Deferred loading reduces prompt size and tool-selection confusion.

### Sandbox

Use container or Kubernetes isolation. Do not enable host bash for production research.

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  replicas: 3
```

Raw evidence should be stored outside the agent's writable workspace or copied into a read-only mount. Hash verification remains mandatory even with read-only storage.

### Guardrails

Enable fail-closed guardrails and restrict tools by agent role. Tool groups reduce what is exposed; guardrails decide whether each attempted call is authorized.

At minimum, block:

- unrestricted host shell;
- arbitrary network exfiltration;
- writes to raw evidence stores;
- writes to approved skills or methodology directories;
- direct release/publishing actions from research agents.

### Custom-agent management API

The official custom-agent API is disabled unless explicitly enabled. Enable it only on a trusted management network, create/sync approved agents, then restrict management access. Do not expose it publicly.

## Codex-to-DeerFlow invocation

Codex calls the official Gateway using `adapters/deerflow_gateway.py`. The adapter follows the official LangGraph-compatible flow:

1. `GET /health`
2. `POST /api/langgraph/threads`
3. `POST /api/langgraph/threads/{thread_id}/runs/stream`

A custom agent is selected through `assistant_id`. DeerFlow routes non-default assistant IDs through the Lead Agent factory with the matching custom-agent configuration.

The adapter records:

- exact request payload;
- selected custom agent and execution mode;
- DeerFlow thread and run IDs;
- full raw SSE event stream;
- final text and artifact references;
- request and event-stream SHA-256 hashes.

These records support operational audit and reproducibility. They are not a substitute for source manifests.

## Recommended execution modes

| Task | DeerFlow mode | Subagents | Notes |
|---|---|---:|---|
| One bounded financial-data request | standard | No | Prefer deterministic MCP call path |
| Industry evidence collection | ultra | Yes, max 2–3 | Parallelize independent source families |
| Quantitative calculation | pro | No by default | Keep one reproducible analysis context |
| Broad mixed research | ultra | Yes | Use only after Codex has produced a task DAG |
| Final independent review | outside main DeerFlow run | No | Preserve reviewer independence |

## Version and compatibility policy

DeerFlow 2.x is a ground-up rewrite and is actively developed. Production integration must pin:

- DeerFlow Git tag or commit;
- config version;
- custom-agent specs;
- enabled skills and their hashes;
- MCP server versions and tool schemas;
- sandbox image digest;
- model/provider configuration.

Do not track `main` or `latest` in a reproducible financial research environment.

## Remaining inputs required from the custom data service

The following are still required before a real end-to-end financial run:

- repository or deployment address;
- HTTP, MCP, CLI, or SDK transport;
- authentication method;
- available dataset catalogue and field dictionary;
- provider/source lineage;
- symbol/entity mapping rules;
- unit, currency, timezone, frequency, and adjustment definitions;
- publication, revision, and point-in-time availability rules;
- pagination, rate limit, retry, and error behavior;
- licensing and permitted storage/use;
- representative fixtures for market, fundamental, macro, filing, and industry data.

Until these exist, the integration can validate the official DeerFlow runtime and the data-plane contract, but it cannot claim the user's financial datasets are production-verified.
