# Multi-Agent Pipeline

A generalised framework for orchestrating multiple AI agents through **gated phases** with **structured output validation**. Runs on the [Claude Code](https://claude.ai/code) Workflow tool (`cc-connect`).

This repository now also contains a finance-research governance overlay for coordinating Codex, Claude Code, Hermes, OpenClaw, DeerFlow, and DeerFlow-style research executors.

## Finance Research Overlay

The finance overlay is built around one rule:

> Financial research must be based on validated facts and reproducible evidence. Agents must not fabricate data, sources, dates, prices, filings, or conclusions.

Core files:

| File | Purpose |
|---|---|
| `AGENTS.md` | Repository-level constitution and non-negotiable agent rules |
| `docs/DATA_TRUST_CONTRACT.md` | Data validation and provenance standard |
| `docs/AGENT_COORDINATION_MODEL.md` | Multi-agent role split across Codex, Claude Code, Hermes, OpenClaw, and DeerFlow |
| `loop/research_loop.yaml` | Machine-readable finance research loop |
| `prompts/CODEX_CHIEF_RESEARCH_PLANNER.md` | Prompt for Codex as chief research planner |
| `schemas/task.schema.json` | Research task contract |
| `schemas/claim.schema.json` | Claim ledger contract |

Recommended finance execution flow:

```text
User / OpenClaw / Hermes
        ↓
Codex qualifies and plans
        ↓
DeerFlow retrieves configured financial data
        ↓
Deterministic validation gates check data
        ↓
Codex or specialist executor analyzes
        ↓
Claude Code performs adversarial review
        ↓
Codex assembles final evidence bundle
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    MULTI-AGENT PIPELINE                          │
│                                                                  │
│  Phase 1         Phase 2        Phase 3        Phase 4          │
│  ┌────────┐     ┌────────┐     ┌────────┐     ┌────────┐       │
│  │VERIFY  │────▶│ GATE   │────▶│EXECUTE │────▶│BRIDGE  │──┐    │
│  │环境验证 │     │数据门控 │     │核心分析 │     │交叉验证 │  │    │
│  └────────┘     └────────┘     └────────┘     └────────┘  │    │
│       │              │              │               │       │    │
│       ▼              ▼              ▼               ▼       │    │
│    ABORT          BLOCK          BLOCK           BLOCK      │    │
│  (环境不满足)   (数据不合格)   (分析失败)    (问题未解决)    │
│                                                             │    │
│  Phase 5         Phase 6                                     │
│  ┌────────┐     ┌────────┐                                  │
│  │OUTPUT  │◀────│RECORD  │◀─────────────────────────────────┘    │
│  │产出生成 │     │归档交接 │                                      │
│  └────────┘     └────────┘                                      │
│                                                                  │
│  ALL phases pass → COMPLETED                                     │
│  Any hard gate fails → Pipeline stops with ABORTED/BLOCKED       │
└─────────────────────────────────────────────────────────────────┘
```

## Core Concepts

### 1. Agent as Phase

Each phase is a standalone AI agent with:
- A **specific role/persona** (defined in the prompt)
- A **JSON Schema** contract for structured output
- **Hard gate logic**: if the phase fails a critical check, the entire pipeline stops

### 2. Structured Output Contracts

Every agent returns validated JSON conforming to a schema. This means:
- Downstream phases receive **guaranteed-shape data**, not free text
- Type mismatches are caught at the schema layer
- The `schema` option on `agent()` enforces this at the tool-call level

### 3. Hard Gates (Fail-Fast)

| Gate | Trigger | Action |
|------|---------|--------|
| VERIFY | `env_ready=false` | ABORT — environment not ready |
| GATE | `overall_pass=false` | BLOCK — data quality insufficient |
| EXECUTE | `status=failed` | BLOCK — core analysis failed |
| BRIDGE | `can_proceed=false` | BLOCK — unresolved CRITICAL findings |

This prevents garbage-in-garbage-out: bad data never reaches the output phase.

### 4. Phase Chaining

Later phases consume outputs from earlier phases via template literals:

```javascript
// Phase 4 (BRIDGE) reads Phase 2 (GATE) results:
const bridge = await agent(
  `Read the gate report at ${gate?.report_path}...`,
  { schema: BRIDGE_SCHEMA }
)

// Phase 5 (OUTPUT) reads Phase 4 (BRIDGE) results:
const output = await agent(
  `Bridge found ${bridge?.total_findings} issues...`,
  { schema: OUTPUT_SCHEMA }
)
```

## Usage

### Quick Start

```bash
# 1. Copy the template
cp pipeline-template.js my-pipeline.js

# 2. Customize the CONFIG block
#    - baseDir, outputDir, name

# 3. Customize each phase's agent prompt
#    - Replace the placeholder instructions with your domain logic

# 4. Customize the schemas if needed

# 5. Run the pipeline
/workflow run my-pipeline
```

### Customising for Your Domain

The template is designed to be **domain-agnostic**. The 6-phase structure works for:

| Domain | Phase 3 (EXECUTE) does | Phase 5 (OUTPUT) produces |
|--------|----------------------|--------------------------|
| Financial Research | Market data analysis, indicator calculation | Research report with charts |
| Code Review | Lint, test, security scan | Review dashboard with findings |
| Content Writing | Research, drafting, fact-checking | Edited article |
| Data Pipeline | ETL, transformation, aggregation | Clean dataset + summary |
| Due Diligence | Multi-source verification, risk scoring | Diligence report |

See `examples/` for domain-specific adaptations.

## Execution Patterns for Phase 3 (EXECUTE)

The EXECUTE phase supports three patterns depending on task complexity:

### Pattern A: Single Agent (simple)
```javascript
const result = await agent(singlePrompt, { schema: EXECUTE_SCHEMA })
```

### Pattern B: Parallel Agents (multi-dimensional)
```javascript
const results = await parallel([
  () => agent(dimensionAPrompt, { label: 'dimA', phase: 'EXECUTE', schema: DIM_SCHEMA }),
  () => agent(dimensionBPrompt, { label: 'dimB', phase: 'EXECUTE', schema: DIM_SCHEMA }),
])
// All dimensions run concurrently — wall-clock = slowest agent
```

### Pattern C: Pipeline (sequential stages per item)
```javascript
const results = await pipeline(
  items,
  item => agent(stage1Prompt(item), { phase: 'EXECUTE' }),
  prev => agent(stage2Prompt(prev), { phase: 'EXECUTE' }),
)
// Each item flows through all stages independently — no barrier between items
```

## Prerequisites

- [Claude Code](https://claude.ai/code) with `cc-connect` installed
- The Workflow tool must be available (included in cc-connect)

## File Structure

```
multi-agent-pipeline/
├── AGENTS.md
├── README.md
├── pipeline-template.js
├── docs/
│   ├── DATA_TRUST_CONTRACT.md
│   └── AGENT_COORDINATION_MODEL.md
├── loop/
│   └── research_loop.yaml
├── prompts/
│   └── CODEX_CHIEF_RESEARCH_PLANNER.md
├── schemas/
│   ├── task.schema.json
│   └── claim.schema.json
└── examples/
    ├── research-report.js
    └── code-review.js
```

## How It Works Under the Hood

1. `Workflow` tool parses the script and discovers `meta.phases` for progress display
2. Each `agent()` call spawns a subagent with the given prompt + schema
3. The subagent returns structured JSON validated against the schema
4. The script evaluates the gate condition; on failure, returns early with status
5. The final `return` value is the pipeline's structured result

## Related Patterns

These patterns can be composed into the pipeline as needed:

| Pattern | Use When |
|---------|----------|
| **Adversarial Verify** | Need to catch plausible-but-wrong outputs — spawn N skeptics, each tries to refute |
| **Judge Panel** | Solution space is wide — N independent attempts, scored by judges, synthesis from winner |
| **Loop-Until-Dry** | Unknown-size discovery (bug finding, edge case hunting) — keep spawning until K rounds return nothing new |
| **Completeness Critic** | Want to avoid blind spots — a final agent asks "what's missing?" |

These are documented in the Workflow tool's help text and can be dropped into any phase.

## License

MIT
