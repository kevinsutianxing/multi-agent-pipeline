# Codex-Led Financial Research Runbook

This runbook turns the repository governance documents into an operational workflow.

The architecture separates four authorities:

```text
Codex external planner and integrator
Official ByteDance DeerFlow 2.x execution runtime
Custom financial-data service connected through MCP
External deterministic controller and independent reviewer
```

Official DeerFlow runs agents; it is not the financial database. The custom financial-data service retrieves and snapshots data; it does not validate itself. Deterministic scripts decide data validity. Claude Code or another separately controlled reviewer challenges the final work.

## 0. Prepare and pin official DeerFlow

Use a pinned official DeerFlow 2.x tag or commit. Do not run a reproducible financial process against moving `main` or an unpinned `latest` sandbox image.

Merge the reviewed profile fragment into official DeerFlow's `config.yaml`:

```text
integrations/deerflow/config.finance-research.example.yaml
```

Key production settings:

- container or Kubernetes sandbox;
- host bash disabled;
- memory injection disabled for research agents;
- Skill Evolution disabled;
- Tool Search enabled for large MCP tool sets;
- token/subagent budgets;
- fail-closed guardrails;
- Custom Agent management API exposed only on a trusted management path.

Register the financial-data MCP adapter using:

```text
integrations/deerflow/extensions_config.finance-research.example.json
```

The module name in that file is intentionally a placeholder. Replace it only with the real custom financial-data MCP server after its transport and tool schemas are known. The service must implement `docs/FINANCE_DATA_MCP_CONTRACT.md`.

Set the official DeerFlow Gateway URLs:

```bash
export DEERFLOW_URL=http://localhost:2026
# Optional explicit overrides:
# export DEERFLOW_GATEWAY_URL=http://localhost:2026
# export DEERFLOW_LANGGRAPH_URL=http://localhost:2026/api/langgraph
```

Verify official DeerFlow:

```bash
python adapters/deerflow_gateway.py health
python adapters/deerflow_gateway.py agents
```

## 1. Synchronize approved DeerFlow Custom Agents

While official DeerFlow's trusted management API is enabled, create or update the approved agent specs:

```bash
for spec in integrations/deerflow/agents/*.json; do
  python adapters/deerflow_gateway.py sync-agent --spec "$spec"
done
```

Approved roles:

- `finance-evidence-agent`: financial-data MCP requests and ID collection only;
- `industry-research-agent`: primary-source discovery, evidence maps, and contradictions;
- `quant-analysis-agent`: reproducible calculations on acquisition-gate-approved data only.

After synchronization, inspect the agent inventory and restrict or disable management access as appropriate:

```bash
python adapters/deerflow_gateway.py agents
```

## 2. Start a research run

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-example"
RUN_DIR="runs/$RUN_ID"

python scripts/research_control.py init \
  --run-dir "$RUN_DIR" \
  --run-id "$RUN_ID" \
  --topic "research topic" \
  --research-type mixed \
  --as-of YYYY-MM-DD
```

The controller creates `research_brief.json` and `run_state.json` in state `INTAKE`.

## 3. Ask Codex to plan

Start external Codex with `prompts/CODEX_CHIEF_RESEARCH_PLANNER.md`. It must read the repository governance and DeerFlow assessment files and create:

```text
runs/<run_id>/research_plan.json
runs/<run_id>/tasks/<task_id>/task.json
runs/<run_id>/tasks/<task_id>/prompt.txt
```

The plan must conform to `schemas/research-plan.schema.json`. It must preregister hypotheses, disconfirming evidence, data requirements, task dependencies, selected Custom Agent, artifact contracts, acceptance commands, retry limits, and human-approval items.

The plan must also distinguish:

- official DeerFlow execution tasks;
- custom financial-data MCP requests;
- deterministic gate commands;
- external independent review.

After reviewing the plan artifact:

```bash
python scripts/research_control.py checkpoint \
  --run-dir "$RUN_DIR" \
  --phase PLANNED
```

## 4. Acquire financial data

Dispatch the bounded task to the official DeerFlow financial evidence Custom Agent:

```bash
python adapters/deerflow_gateway.py run \
  --run-dir "$RUN_DIR" \
  --task-id collect-financial-data \
  --agent finance-evidence-agent \
  --mode standard \
  --message-file "$RUN_DIR/tasks/collect-financial-data/prompt.txt"
```

The agent may call only approved financial-data MCP tools. The custom financial-data service must preserve provider responses and create:

```text
runs/<run_id>/raw/...
runs/<run_id>/source_manifest.data.json
runs/<run_id>/dataset_manifest.json
```

Every snapshot result must conform to `schemas/finance-data-snapshot.schema.json` and initially use `validation_status: PENDING`.

The official DeerFlow adapter separately creates:

```text
runs/<run_id>/deerflow/collect-financial-data/request.json
runs/<run_id>/deerflow/collect-financial-data/events.jsonl
runs/<run_id>/deerflow/collect-financial-data/result.json
```

These files prove what was asked and executed. They do not prove that the financial values are correct.

## 5. Acquire industry and company evidence

Dispatch a separate task:

```bash
python adapters/deerflow_gateway.py run \
  --run-dir "$RUN_DIR" \
  --task-id collect-industry-evidence \
  --agent industry-research-agent \
  --mode ultra \
  --max-subagents 3 \
  --message-file "$RUN_DIR/tasks/collect-industry-evidence/prompt.txt"
```

The industry agent may use generic web search and fetch for discovery. Search snippets and model summaries are not accepted evidence. Material sources must be preserved through an approved capture tool and recorded in:

```text
runs/<run_id>/source_manifest.research.json
runs/<run_id>/evidence_maps/...
runs/<run_id>/contradiction_register.json
```

Financial-data and industry-evidence tasks may run in parallel, but they must write different manifest segments.

After all declared acquisition artifacts exist:

```bash
python scripts/research_control.py checkpoint \
  --run-dir "$RUN_DIR" \
  --phase ACQUIRED
```

## 6. Run the acquisition gate

```bash
python scripts/research_control.py gate \
  --run-dir "$RUN_DIR" \
  --stage acquisition
```

The controller runs the manifest merger and deterministic evidence validator. It checks snapshots, hashes, dates, missingness, duplicates, point-in-time availability, proxies, and metadata.

A successful provider response, official DeerFlow result, MCP result, or agent `overall_pass=true` is not sufficient.

A passing run moves to `DATA_VALIDATED`. A critical failure moves to `BLOCKED_DATA` and preserves `acquisition_gate_report.json`.

## 7. Execute quantitative and/or industry analysis

Codex assigns bounded analysis tasks only after `DATA_VALIDATED`.

### Quantitative execution through official DeerFlow

```bash
python adapters/deerflow_gateway.py run \
  --run-dir "$RUN_DIR" \
  --task-id quant-analysis \
  --agent quant-analysis-agent \
  --mode pro \
  --message-file "$RUN_DIR/tasks/quant-analysis/prompt.txt"
```

The quantitative agent must not have live web search or unvalidated financial-data tools.

Require at least:

- economic mechanism and preregistered hypothesis;
- point-in-time universe and identifier mapping;
- corporate actions and adjustment convention;
- survivorship, revision, feature, and label leakage controls;
- train/validation/test or walk-forward evaluation;
- benchmark and risk-model rationale;
- transaction costs, slippage, liquidity, turnover, and capacity;
- multiple-testing controls;
- subperiod, sensitivity, and ablation analysis;
- statistical and economic significance;
- reproducible seeds and environment.

### Industry/company analysis

Require at least:

- value-chain taxonomy and entity map;
- primary-source hierarchy;
- publication and availability dates;
- KPI, unit, currency, and accounting comparability;
- demand, supply, price, inventory, capacity, utilization, market share, margins, and cash-flow mapping where relevant;
- historical base rates and cycle comparisons;
- alternative causal explanations;
- bull/base/bear assumptions and disconfirming indicators;
- explicit contradictory evidence.

Required outputs:

```text
runs/<run_id>/calculation_manifest.json
runs/<run_id>/claim_ledger.jsonl
runs/<run_id>/analysis/...
```

Then:

```bash
python scripts/research_control.py checkpoint \
  --run-dir "$RUN_DIR" \
  --phase ANALYZED
```

## 8. Reproduce material outputs

Regenerate material calculations, tables, and figures in a clean process. Record the environment, pinned official DeerFlow version where relevant, Git commit, sandbox image digest, commands, seeds, input hashes, output hashes, warnings, and differences in:

```text
runs/<run_id>/reproducibility_report.json
```

The report must contain `"status": "PASS"` before the controller accepts it:

```bash
python scripts/research_control.py checkpoint \
  --run-dir "$RUN_DIR" \
  --phase REPRODUCED
```

## 9. Run the release-data gate

```bash
python scripts/research_control.py gate \
  --run-dir "$RUN_DIR" \
  --stage release
```

This validates calculation lineage, claim references, contradiction status, and 100% support coverage for material claims. The report is stored separately as `release_data_gate_report.json`.

## 10. Perform independent adversarial review

Start a genuinely separate Claude Code session or another approved reviewer outside the primary official DeerFlow run. Give it:

- research brief and approved plan;
- source and dataset manifests;
- acquisition and release-data gate reports;
- official DeerFlow `request.json`, `events.jsonl`, and `result.json` audit records;
- code and relevant diff;
- calculation manifest and outputs;
- claim ledger;
- candidate charts/report if available.

Do not give it the implementer's private reasoning and do not instruct it that the work should pass.

An ACP Claude process called by the same official DeerFlow run may be used as an implementation critic. It does not satisfy final release independence by itself.

The reviewer writes:

```json
{
  "status": "PASS",
  "critical_count": 0,
  "warning_count": 0,
  "findings": []
}
```

to `runs/<run_id>/review_report.json`. Then record the verdict:

```bash
python scripts/research_control.py review --run-dir "$RUN_DIR"
```

If independent review is unavailable, stop with `NEEDS_HUMAN`; do not simulate it.

## 11. Synthesize and release

Codex creates the candidate report using only verified claim-ledger records and reproducible calculations. It also writes `release_requirements.json`, for example:

```json
{
  "methodology_changed": false,
  "investment_recommendation": false,
  "material_source_conflict": false,
  "proxy_substitution_affects_conclusion": false,
  "human_approved": false
}
```

If any sensitive flag is true, `human_approved` must be true before release.

```bash
python scripts/research_control.py release \
  --run-dir "$RUN_DIR" \
  --candidate candidate_report.md
```

Release requires both keys:

1. deterministic acquisition/release-data and reproducibility reports are `PASS`;
2. independent review is `PASS` with zero critical findings.

## 12. Hermes and OpenClaw integration

### Hermes

Use Hermes to retrieve approved source quirks and procedures before planning, and to write post-run lessons only under candidate memory/skill paths. Promotion requires regression evidence and independent approval.

Do not use official DeerFlow conversational memory or Hermes memory as financial evidence.

### OpenClaw

Use OpenClaw for schedules, webhooks, heartbeat checks, and notifications. It may create intake tasks and report terminal states. It must not alter gate reports, waive failures, or publish research conclusions.

## 13. Inspect current state

```bash
python scripts/research_control.py status --run-dir "$RUN_DIR"
```

The conversation history of Codex, official DeerFlow, Claude Code, Hermes, or OpenClaw is not run state. `run_state.json` and preserved artifacts are the source of truth.

## 14. Current integration stop condition

Do not claim a production end-to-end run until the real custom financial-data service provides:

- repository or deployment location;
- MCP, HTTP, CLI, or SDK transport;
- authentication method;
- dataset catalogue and field dictionary;
- entity mapping rules;
- units, currency, timezone, frequency, revisions, and adjustments;
- publication/availability-time semantics;
- rate-limit and error behavior;
- licensing constraints;
- market, fundamental, macro, filing, and industry fixtures.

Until then, only the official DeerFlow runtime adapter, Custom Agent contracts, deterministic gates, and placeholder financial-data interface can be tested.
