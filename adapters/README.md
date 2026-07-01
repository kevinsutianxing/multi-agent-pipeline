# Runtime Adapter Guide

The research protocol is platform-neutral. Each runtime is an adapter around the same task envelope, artifact paths, and deterministic gates.

## System boundary

There are two distinct DeerFlow components:

```text
Official ByteDance DeerFlow 2.x
  = agent harness, custom agents, subagents, skills, MCP, sandbox, memory, Gateway

Custom financial-data DeerFlow service
  = market/fundamental/macro/filing/industry data plane
```

Do not combine them into one trust boundary. Official DeerFlow may call the financial service through MCP; it does not make the data valid.

## Codex

Use Codex as the external Chief Research Planner and Integrator. It should load root `AGENTS.md`, create a run directory, emit a schema-valid plan, and execute one bounded task attempt at a time.

Suggested non-interactive pattern:

```bash
codex exec \
  --sandbox workspace-write \
  --output-schema schemas/task-result.schema.json \
  -o runs/$RUN_ID/tasks/$TASK_ID/result.json \
  "Read AGENTS.md and execute task envelope runs/$RUN_ID/tasks/$TASK_ID/task.json"
```

Codex decides task decomposition and integration, but the external controller runs acceptance commands, advances state, counts retries, and decides release. Codex prose must not be treated as a gate result.

## Official DeerFlow Gateway

`adapters/deerflow_gateway.py` calls a running official ByteDance DeerFlow 2.x instance through its Gateway and LangGraph-compatible API.

Environment:

```bash
export DEERFLOW_URL=http://localhost:2026
# Optional overrides:
# export DEERFLOW_GATEWAY_URL=http://localhost:2026
# export DEERFLOW_LANGGRAPH_URL=http://localhost:2026/api/langgraph
```

Health and agent inventory:

```bash
python adapters/deerflow_gateway.py health
python adapters/deerflow_gateway.py agents
```

Synchronize an approved Custom Agent spec while the management API is enabled:

```bash
python adapters/deerflow_gateway.py sync-agent \
  --spec integrations/deerflow/agents/finance-evidence-agent.json
```

Execute a bounded task:

```bash
python adapters/deerflow_gateway.py run \
  --run-dir runs/$RUN_ID \
  --task-id collect-market-data \
  --agent finance-evidence-agent \
  --mode standard \
  --message-file runs/$RUN_ID/tasks/collect-market-data/prompt.txt
```

The adapter preserves:

```text
runs/<run_id>/deerflow/<task_id>/request.json
runs/<run_id>/deerflow/<task_id>/events.jsonl
runs/<run_id>/deerflow/<task_id>/result.json
```

These files contain the exact request, custom agent, execution mode, DeerFlow thread/run IDs, raw SSE events, response/artifact references, and hashes. They are operational audit records, not financial source evidence.

### Execution-mode guidance

| Task | Mode | Subagents |
|---|---|---:|
| Bounded financial MCP request | `standard` | No |
| Industry evidence collection | `ultra` | Yes, normally 2–3 |
| Quantitative calculation | `pro` | No by default |
| Broad mixed evidence task | `ultra` | Only after Codex task decomposition |

## Official DeerFlow Custom Agents

Approved specs live under:

```text
integrations/deerflow/agents/
```

- `finance-evidence-agent`: approved financial-data MCP tools only; no conclusions or self-validation.
- `industry-research-agent`: primary-source and contradiction collection; web tools are discovery only.
- `quant-analysis-agent`: validated datasets and sandbox calculations only; no live unvalidated data.

Use Custom Agent model, Skill, and Tool Group whitelists to minimize authority. Do not give every agent every tool.

## Custom financial-data service

The custom data service is connected through an MCP server or equivalent narrow tool adapter described in:

```text
docs/FINANCE_DATA_MCP_CONTRACT.md
schemas/finance-data-snapshot.schema.json
integrations/deerflow/extensions_config.finance-research.example.json
```

Its logical operation is:

```text
bounded request
  -> provider request
  -> immutable raw snapshot
  -> normalized snapshot
  -> source/dataset metadata
  -> validation_status=PENDING
  -> deterministic acquisition gate
```

Required behavior:

- credentials redacted from all manifests and agent-visible output;
- stable entity resolution with effective dates;
- immutable raw responses and SHA-256 hashes;
- publication, availability, observation, retrieval, and as-of times kept distinct;
- explicit units, scale, currency, timezone, frequency, accounting scope, revision and adjustment conventions;
- structured errors and bounded retries;
- no self-certification or research conclusions.

## Claude Code

Use Claude Code for complex implementation/debugging and as the independent adversarial release reviewer.

The final reviewer receives the brief, approved plan, manifests, code diff, deterministic gate reports, calculation artifacts, claim ledger, and candidate report. It must run outside the primary DeerFlow execution and produce a separate `review_report.json`.

An ACP Claude process spawned by the same DeerFlow parent can be useful as an implementation critic, but context/process separation alone does not satisfy final release independence.

Do not give the reviewer the implementer's private reasoning or instruct it that the result is expected to pass.

## Hermes

At task start, Hermes may retrieve approved skills and source notes. New observations go only to candidate memory/skill directories until regression-tested and approved.

Do not use conversationally extracted DeerFlow memory as financial evidence. Production DeerFlow research agents should have memory injection disabled.

A new cron/session must recover from `run_state.json`; conversational memory is not run state.

## OpenClaw

Use cron, webhooks, and heartbeat for:

- creating intake tasks;
- checking stalled runs;
- triggering scheduled data refreshes;
- reporting terminal-state transitions;
- surfacing external-source outages.

OpenClaw must not alter gate reports, waive failures, or publish financial conclusions.

## Security profile

For production official DeerFlow:

- pin a Git tag or commit and sandbox image digest;
- use container or Kubernetes sandboxing;
- keep host bash disabled;
- disable Skill Evolution;
- disable memory injection for research agents;
- enable tool search for large MCP tool sets;
- enable fail-closed guardrails;
- keep the Custom Agent management API on a trusted management network only;
- mount approved skills and methodology read-only;
- keep raw evidence immutable and hash-verified.
