# Multi-Agent Pipeline

A generalised framework for orchestrating multiple AI agents through **gated phases** with **structured output validation**. The original templates run on the Claude Code Workflow tool (`cc-connect`).

The repository also contains a stricter financial-research system led by external Codex and backed by deterministic evidence gates.

## Financial Research System

The financial overlay is built around one rule:

> Financial research must be based on validated facts and reproducible evidence. Agents must not fabricate data, sources, dates, prices, filings, service capabilities, or conclusions.

### DeerFlow naming boundary

This system distinguishes two separate components:

- **Official ByteDance DeerFlow 2.x:** agent execution harness with Custom Agents, subagents, Skills, MCP, Sandbox, memory, Gateway APIs, and run events.
- **Custom financial-data DeerFlow service:** separate market/fundamental/macro/filing/industry data plane connected through MCP or an equivalent narrow adapter.

Official DeerFlow is not the financial database. The custom data service is not the research planner or reviewer.

### Recommended architecture

```text
User / OpenClaw / Hermes
        |
        v
External Codex chief planner
        |
        v
External deterministic state controller
        |
        v
Official DeerFlow 2.x execution runtime
   |              |                |
finance-       industry-         quant-
evidence       research          analysis
agent          agent             agent
   \              |                /
        custom financial-data MCP
                    |
        immutable snapshots + metadata
                    |
          deterministic data gates
                    |
        external independent reviewer
                    |
             controlled release
```

Agent output, agent consensus, MCP success, and JSON-shaped `overall_pass=true` are not financial validation evidence.

### Core files

| File | Purpose |
|---|---|
| `AGENTS.md` | Repository-level financial research constitution |
| `docs/DATA_TRUST_CONTRACT.md` | Data trust levels, provenance, and validation standard |
| `docs/AGENT_COORDINATION_MODEL.md` | Multi-agent responsibility model |
| `docs/DEERFLOW_CAPABILITY_ASSESSMENT.md` | Official DeerFlow capabilities, limits, and architecture decision |
| `docs/FINANCE_DATA_MCP_CONTRACT.md` | Snapshot-first contract for the custom financial-data service |
| `docs/EXECUTABLE_RESEARCH_GATES.md` | Deterministic evidence and claim gates |
| `docs/CODEX_LED_RESEARCH_RUNBOOK.md` | End-to-end operating procedure |
| `loop/research_execution_profile.yaml` | Machine-readable enforced execution profile |
| `prompts/CODEX_CHIEF_RESEARCH_PLANNER.md` | Codex chief planner operating prompt |
| `adapters/deerflow_gateway.py` | Auditable official DeerFlow Gateway/SSE adapter |
| `scripts/deerflow_preflight.py` | Deployment, MCP, agent, and security preflight |
| `scripts/research_control.py` | External state and release controller |
| `scripts/validate_evidence.py` | Snapshot, timing, lineage, and claim validator |
| `integrations/deerflow/` | Official DeerFlow config, Custom Agent specs, and deployment templates |

### Enforced financial state progression

```text
INTAKE
-> PLANNED
-> DEERFLOW_READY
-> ACQUIRED
-> DATA_VALIDATED
-> ANALYZED
-> REPRODUCED
-> RELEASE_DATA_VALIDATED
-> REVIEWED
-> COMPLETED
```

Preflight, acquisition validation, release validation, reproducibility, and independent review are hard gates. The controller reruns live DeerFlow preflight at release.

### Start here

```text
1. Read AGENTS.md and the Data Trust Contract.
2. Read the DeerFlow capability assessment and financial-data MCP contract.
3. Configure a pinned official DeerFlow deployment and the real financial-data MCP server.
4. Follow docs/CODEX_LED_RESEARCH_RUNBOOK.md.
5. Keep the PR/run blocked until real market, fundamental, macro, filing, and industry fixtures pass end to end.
```

## Generic Six-Phase Architecture

The original domain-agnostic template remains useful for non-financial or lower-assurance workflows:

```text
VERIFY -> GATE -> EXECUTE -> BRIDGE -> OUTPUT -> RECORD
```

For high-assurance financial research, the model-declared `GATE` in the generic template is not sufficient by itself. Use the external controller and deterministic financial gates described above.

## Core Concepts

### 1. Agent as Phase

Each phase is a standalone AI agent with:

- a specific role/persona;
- a JSON Schema contract for structured output;
- hard gate logic that stops the pipeline on critical failure.

### 2. Structured Output Contracts

Every agent returns validated JSON conforming to a schema. This gives downstream phases a guaranteed data shape and catches type mismatches.

Schema validation proves shape, not factual correctness. Financial values require snapshot-backed provenance and deterministic checks.

### 3. Hard Gates

| Generic gate | Trigger | Action |
|---|---|---|
| VERIFY | `env_ready=false` | ABORT — environment not ready |
| GATE | `overall_pass=false` | BLOCK — input quality insufficient |
| EXECUTE | `status=failed` | BLOCK — core analysis failed |
| BRIDGE | `can_proceed=false` | BLOCK — unresolved critical findings |

### 4. Phase Chaining

Later phases consume outputs from earlier phases:

```javascript
const bridge = await agent(
  `Read the gate report at ${gate?.report_path}...`,
  { schema: BRIDGE_SCHEMA }
)

const output = await agent(
  `Bridge found ${bridge?.total_findings} issues...`,
  { schema: OUTPUT_SCHEMA }
)
```

## Generic Template Usage

```bash
cp pipeline-template.js my-pipeline.js
# Customize CONFIG, prompts, and schemas.
/workflow run my-pipeline
```

The six-phase template can be adapted for code review, content, ETL, due diligence, and other domains.

## Execution Patterns

### Single agent

```javascript
const result = await agent(singlePrompt, { schema: EXECUTE_SCHEMA })
```

### Parallel agents

```javascript
const results = await parallel([
  () => agent(dimensionAPrompt, { label: 'dimA', phase: 'EXECUTE', schema: DIM_SCHEMA }),
  () => agent(dimensionBPrompt, { label: 'dimB', phase: 'EXECUTE', schema: DIM_SCHEMA }),
])
```

### Per-item pipeline

```javascript
const results = await pipeline(
  items,
  item => agent(stage1Prompt(item), { phase: 'EXECUTE' }),
  prev => agent(stage2Prompt(prev), { phase: 'EXECUTE' }),
)
```

## Repository Structure

```text
multi-agent-pipeline/
├── AGENTS.md
├── README.md
├── pipeline-template.js
├── adapters/
│   ├── README.md
│   └── deerflow_gateway.py
├── docs/
│   ├── AGENT_COORDINATION_MODEL.md
│   ├── CODEX_LED_RESEARCH_RUNBOOK.md
│   ├── DATA_TRUST_CONTRACT.md
│   ├── DEERFLOW_CAPABILITY_ASSESSMENT.md
│   ├── EXECUTABLE_RESEARCH_GATES.md
│   └── FINANCE_DATA_MCP_CONTRACT.md
├── integrations/deerflow/
│   ├── agents/
│   ├── config.finance-research.example.yaml
│   ├── deployment-manifest.example.json
│   └── extensions_config.finance-research.example.json
├── loop/
│   ├── research_loop.yaml
│   └── research_execution_profile.yaml
├── prompts/
│   └── CODEX_CHIEF_RESEARCH_PLANNER.md
├── schemas/
├── scripts/
│   ├── deerflow_preflight.py
│   ├── merge_manifests.py
│   ├── research_control.py
│   └── validate_evidence.py
├── tests/
└── examples/
    ├── research-report.js
    └── code-review.js
```

## Related Patterns

| Pattern | Use when |
|---|---|
| Adversarial Verify | Need to catch plausible-but-wrong outputs |
| Judge Panel | Solution space is broad and independent attempts help |
| Loop-Until-Dry | Discovery size is unknown |
| Completeness Critic | Need a final blind-spot review |

These patterns improve exploration but do not replace source evidence, deterministic gates, or independent release review.

## License

MIT
