# DeerFlow Capability Assessment and Architecture Decision

**Assessment date:** 2026-07-01  
**Official project:** `bytedance/deer-flow`  
**Assessed upstream baseline:** commit `e5424cbab9a2a1ec9a09aa9d4c6737aab7ad42c1` on the DeerFlow 2.x line

This assessment is version-specific. Re-run it when the pinned production DeerFlow version changes materially.

## Executive decision

The system contains two different components that share the DeerFlow name:

1. **Official ByteDance DeerFlow 2.x** — a LangGraph/LangChain agent execution harness with Custom Agents, subagents, Skills, MCP tools, Sandbox execution, memory, Gateway APIs, tracing, and ACP delegation.
2. **The user's custom DeerFlow financial-data service** — a separate data plane whose concrete transport, authentication, dataset catalogue, and field semantics are not yet documented in this repository.

They must not share one trust boundary.

```text
External Codex chief planner and integrator
                    |
                    v
         deterministic run controller
                    |
            official DeerFlow Gateway
       /              |                \
finance-evidence  industry-research  quant-analysis
 Custom Agent       Custom Agent      Custom Agent
       \              |                /
                    MCP
                    |
       custom financial-data service
                    |
       immutable snapshots + metadata + hashes
                    |
       deterministic evidence and release gates
                    |
        external independent reviewer
```

Official DeerFlow is the **agent execution runtime**. The custom financial-data service is the **financial data plane**. Codex remains the external research planner. Deterministic scripts and a separately controlled reviewer remain the release authority.

## What official DeerFlow is good at

### Long-horizon execution

DeerFlow provides a Lead Agent, persistent threads, planning mode, bounded recursion, token budgets, loop detection, recovery handling, Sandbox tools, and artifact presentation. It is suitable for multi-step evidence collection and reproducible artifact production.

### Scoped parallel work

Built-in and Custom subagents run with isolated contexts and can execute in parallel. Custom Agents can be restricted by model, Skill whitelist, and Tool Group whitelist.

Official source review confirmed that delegated subagents inherit the parent Custom Agent's Tool Groups, and their Skills are constrained by the parent policy. This makes bounded industry-research parallelism viable when global Guardrails are also enabled.

### External agent delegation

ACP can invoke Codex, Claude Code, and other compatible agents. This is useful for bounded implementation and debugging.

ACP process separation is not sufficient final-review independence. A reviewer spawned under the same primary DeerFlow run remains part of that execution authority.

### Extensible data access

MCP and Python tools are the correct extension points for the user's financial-data service. Financial data should not be embedded in agent memory or inferred from model knowledge.

### Sandbox and observability

DeerFlow supports local, container, E2B, and Kubernetes-style Sandbox providers and streams detailed run events. Gateway thread/run IDs and tracing are valuable operational evidence.

Operational traces do not prove financial facts. Research still requires immutable source snapshots, query parameters, hashes, publication/availability timing, calculation lineage, and Claim IDs.

## What official DeerFlow does not guarantee

### Financial semantics

DeerFlow does not inherently know whether:

- prices are raw, split-adjusted, dividend-adjusted, or total-return;
- a financial statement value is cumulative or single-quarter;
- an index constituent list is point-in-time;
- a macro series is original or revised;
- an entity/ticker mapping was valid on a historical date;
- units, currencies, accounting scope, and filing dates are comparable.

These guarantees belong in the custom financial-data service and deterministic validation layer.

### Citation truth

A research agent can discover and summarize sources, but its prose is not proof that a source exists or supports a Claim. Material evidence must be preserved as a snapshot and assigned a stable evidence ID.

### Reviewer independence

Subagents and ACP agents provide context/process separation, not organizational or release independence. Final review must be controlled separately from the primary DeerFlow run.

### Safe autonomous Skill evolution

DeerFlow can create or improve Skills. Production financial research must disable Skill Evolution because a single run must not silently alter future methodology. Approved Skills should be versioned, reviewed, regression-tested, and mounted read-only.

### Research-safe memory by default

DeerFlow can extract facts from conversations and inject them into later prompts. This may contaminate point-in-time research with stale or unsupported facts. Production research Custom Agents should have memory injection disabled.

## Approved Custom Agent roles

### `finance-evidence-agent`

Owns bounded MCP requests, evidence/dataset ID collection, and data-gap reporting.

It may not:

- validate its own data;
- issue investment conclusions;
- silently map tickers, backfill data, convert units, or substitute proxies;
- invent metadata that should come from the financial-data adapter.

### `industry-research-agent`

Owns value-chain mapping, primary-source discovery, industry evidence maps, and contradiction collection.

Generic search/fetch is discovery only. Material facts must resolve to snapshot-backed evidence IDs.

### `quant-analysis-agent`

Owns reproducible calculations on acquisition-gate-approved datasets.

It may not access live unvalidated data, modify raw snapshots, change methodology after seeing results, or decide release.

## Financial-data MCP decision

The user's custom service should be connected through a narrow snapshot-first MCP server or equivalent adapter.

```text
bounded request
  -> provider request
  -> immutable raw snapshot
  -> normalized snapshot
  -> source/dataset metadata
  -> validation_status=PENDING
  -> deterministic acquisition gate
```

A tool call that only returns rows, a DataFrame preview, prose, or `success=true` is insufficient.

Recommended initial logical tools:

- `resolve_financial_entity`
- `fetch_market_data_snapshot`
- `fetch_fundamental_snapshot`
- `fetch_macro_snapshot`
- `fetch_filing_snapshot`
- `fetch_industry_dataset_snapshot`
- `describe_dataset`
- `list_data_revisions`
- `capture_web_evidence_snapshot`

The full contract is in `docs/FINANCE_DATA_MCP_CONTRACT.md` and `schemas/finance-data-snapshot.schema.json`.

## Production profile decisions

### Pin everything material

Production must pin:

- official DeerFlow tag or commit;
- config version and hash;
- Custom Agent specs;
- enabled Skills and hashes;
- MCP server versions and tool schemas;
- Sandbox image digest;
- model/provider configuration.

Do not track `main`, `master`, `HEAD`, or `latest`.

### Memory and Skills

```yaml
memory:
  enabled: true
  injection_enabled: false

skill_evolution:
  enabled: false

tool_search:
  enabled: true
```

Memory storage may remain for operational review, but extracted memory must not enter the financial evidence chain.

### Sandbox

Use container, Kubernetes, or E2B isolation. Host bash must remain disabled. Raw evidence should be immutable or read-only and hash-verified.

### Guardrails

Use explicit per-Agent Tool Groups plus fail-closed global Guardrails. The built-in allowlist is a second boundary, not a substitute for argument/path/network-aware production policy.

At minimum block:

- Custom Agent self-modification (`update_agent`/`setup_agent`);
- unrestricted ACP delegation from production research Agents;
- arbitrary host shell and network exfiltration;
- writes to raw evidence, approved Skills, and methodology directories;
- publishing/release actions from research Agents.

### Custom Agent management API

Enable it only on a trusted management path for synchronization. Restrict or disable it afterward. Preflight must record the synchronization timestamp and expected Agent inventory.

## Codex-to-DeerFlow invocation

`adapters/deerflow_gateway.py` follows the official Gateway/LangGraph-compatible flow:

1. `GET /health`
2. `POST /api/langgraph/threads`
3. `POST /api/langgraph/threads/{thread_id}/runs/stream`

A Custom Agent is selected by `assistant_id`. The adapter preserves:

- exact request payload;
- selected Agent and execution mode;
- DeerFlow thread/run IDs;
- full raw SSE event stream;
- final response and artifact references;
- request and event-stream SHA-256 hashes.

These records support execution audit and reproducibility, not financial source validation.

## Recommended execution modes

| Task | Mode | Subagents | Decision |
|---|---|---:|---|
| Bounded financial MCP request | `standard` | No | Prefer direct, narrow data requests |
| Industry evidence collection | `ultra` | 2–3 | Parallelize independent source families |
| Quantitative calculation | `pro` | No by default | Keep one reproducible analysis context |
| Broad mixed evidence task | `ultra` | Bounded | Only after Codex creates a task DAG |
| Final independent review | Outside primary run | No | Preserve release independence |

## Enforced preflight and release behavior

The external controller requires:

```text
INTAKE -> PLANNED -> DEERFLOW_READY -> ACQUIRED
```

It cannot enter `ACQUIRED` directly from `PLANNED`.

Preflight checks:

- pinned official ref and Sandbox image;
- config and extensions hashes;
- isolated Sandbox and host-bash policy;
- memory, Skill Evolution, Tool Search, and Guardrail policy;
- placeholder-free financial MCP configuration;
- official DeerFlow health;
- approved Custom Agent inventory when management access permits.

Release reruns live DeerFlow preflight using the same recorded deployment inputs. Missing or malformed reports fail closed.

## Remaining inputs required from the custom financial-data service

A real end-to-end financial run still requires:

- repository or deployment address;
- HTTP, MCP, CLI, or SDK transport;
- authentication method;
- dataset catalogue and field dictionary;
- provider/source lineage;
- entity/symbol mapping rules;
- unit, currency, timezone, frequency, adjustment, accounting, and revision definitions;
- publication and point-in-time availability rules;
- pagination, rate-limit, retry, and error behavior;
- licensing and permitted storage/use;
- representative market, fundamental, macro, filing, and industry fixtures.

Until these exist, the repository can validate the official DeerFlow runtime integration, security profile, adapter contracts, and deterministic gates, but it cannot claim the user's financial datasets are production-verified.
