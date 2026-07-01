# Codex-Led Financial Research Runbook

This runbook operates four separate authorities:

```text
Codex external planner and integrator
Official ByteDance DeerFlow 2.x execution runtime
Custom financial-data service connected through MCP
External deterministic controller and independent reviewer
```

Official DeerFlow runs agents; it is not the financial database. The custom financial-data service retrieves and snapshots data; it does not validate itself. Deterministic scripts decide data validity. Claude Code or another separately controlled reviewer challenges the final work.

## 0. Prepare and pin official DeerFlow

Use a reviewed official DeerFlow 2.x tag or commit. Do not run reproducible financial research against moving `main`, `master`, `HEAD`, or an unpinned `latest` sandbox image.

Use these templates:

```text
integrations/deerflow/config.finance-research.example.yaml
integrations/deerflow/extensions_config.finance-research.example.json
integrations/deerflow/deployment-manifest.example.json
```

The real deployment must:

- use container, Kubernetes, or E2B isolation;
- keep host bash disabled;
- disable memory injection for research agents;
- disable Skill Evolution;
- enable Tool Search for large MCP sets;
- use explicit Tool Groups and fail-closed Guardrails;
- pin the DeerFlow ref and sandbox image;
- replace the placeholder financial-data MCP module;
- record hashes for the deployed config and extensions config.

The custom financial-data MCP server must implement:

```text
docs/FINANCE_DATA_MCP_CONTRACT.md
schemas/finance-data-snapshot.schema.json
```

Set official DeerFlow Gateway URLs:

```bash
export DEERFLOW_URL=http://localhost:2026
# Optional overrides:
# export DEERFLOW_GATEWAY_URL=http://localhost:2026
# export DEERFLOW_LANGGRAPH_URL=http://localhost:2026/api/langgraph
```

## 1. Synchronize approved Custom Agents

While the trusted Custom Agent management API is enabled:

```bash
for spec in integrations/deerflow/agents/*.json; do
  python adapters/deerflow_gateway.py sync-agent --spec "$spec"
done
```

Approved roles:

- `finance-evidence-agent`: bounded financial-data MCP requests; no conclusions or self-validation;
- `industry-research-agent`: primary-source discovery, evidence maps, and contradictions;
- `quant-analysis-agent`: reproducible calculations on acquisition-gate-approved data only.

Record the synchronization timestamp in the real deployment manifest. Restrict or disable management access afterward.

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

Start external Codex with `prompts/CODEX_CHIEF_RESEARCH_PLANNER.md`. It creates:

```text
runs/<run_id>/research_plan.json
runs/<run_id>/tasks/<task_id>/task.json
runs/<run_id>/tasks/<task_id>/prompt.txt
```

The plan must preregister hypotheses, disconfirming evidence, point-in-time requirements, selected Custom Agents, data/MCP requests, artifacts, acceptance commands, retry limits, and human-approval items.

Then:

```bash
python scripts/research_control.py checkpoint \
  --run-dir "$RUN_DIR" \
  --phase PLANNED
```

## 4. Run controlled DeerFlow preflight

Copy and complete the deployment templates outside the repository examples. The repository examples intentionally fail preflight until placeholders, hashes, pinned versions, and synchronization timestamps are replaced.

```bash
python scripts/research_control.py deerflow-preflight \
  --run-dir "$RUN_DIR" \
  --deployment-manifest /path/to/deployment-manifest.json \
  --config /path/to/deer-flow/config.yaml \
  --extensions-config /path/to/deer-flow/extensions_config.json
```

When the Custom Agent management API has been disabled after synchronization, add:

```bash
--skip-live-agent-inventory
```

This skips only the live `/api/agents` check. It does not skip official DeerFlow health, version pinning, hashes, MCP configuration, placeholder detection, Sandbox controls, Memory policy, Skill Evolution policy, or Guardrails policy.

A pass moves the run to `DEERFLOW_READY`. A failure moves it to `BLOCKED_EXTERNAL`. The run cannot enter `ACQUIRED` directly from `PLANNED`.

## 5. Acquire financial data

Dispatch a bounded task through the official DeerFlow runtime:

```bash
python adapters/deerflow_gateway.py run \
  --run-dir "$RUN_DIR" \
  --task-id collect-financial-data \
  --agent finance-evidence-agent \
  --mode standard \
  --message-file "$RUN_DIR/tasks/collect-financial-data/prompt.txt"
```

The Custom Agent may call only approved financial-data MCP tools. The custom financial-data service—not the model—must preserve provider responses and create:

```text
runs/<run_id>/raw/...
runs/<run_id>/source_manifest.data.json
runs/<run_id>/dataset_manifest.json
```

Every snapshot result starts with `validation_status: PENDING`.

The official DeerFlow adapter separately preserves operational audit records:

```text
runs/<run_id>/deerflow/collect-financial-data/request.json
runs/<run_id>/deerflow/collect-financial-data/events.jsonl
runs/<run_id>/deerflow/collect-financial-data/result.json
```

These records prove what was requested and executed. They do not prove that financial values are correct.

## 6. Acquire industry and company evidence

```bash
python adapters/deerflow_gateway.py run \
  --run-dir "$RUN_DIR" \
  --task-id collect-industry-evidence \
  --agent industry-research-agent \
  --mode ultra \
  --max-subagents 3 \
  --message-file "$RUN_DIR/tasks/collect-industry-evidence/prompt.txt"
```

Generic web search/fetch is discovery only. Search snippets and model summaries are not accepted evidence. Material sources must be captured through an approved snapshot tool and recorded in:

```text
runs/<run_id>/source_manifest.research.json
runs/<run_id>/evidence_maps/...
runs/<run_id>/contradiction_register.json
```

Financial-data and industry-evidence tasks may run in parallel, but they write different manifest segments.

After all declared acquisition artifacts exist:

```bash
python scripts/research_control.py checkpoint \
  --run-dir "$RUN_DIR" \
  --phase ACQUIRED
```

## 7. Run the acquisition gate

```bash
python scripts/research_control.py gate \
  --run-dir "$RUN_DIR" \
  --stage acquisition
```

The controller merges manifests and validates snapshots, hashes, dates, missingness, duplicates, point-in-time availability, proxies, and metadata.

A provider success flag, DeerFlow result, MCP result, or agent `overall_pass=true` is not sufficient.

A pass moves the run to `DATA_VALIDATED`. A critical failure moves it to `BLOCKED_DATA` and preserves `acquisition_gate_report.json`.

## 8. Execute quantitative and/or industry analysis

Codex assigns analysis only after `DATA_VALIDATED`.

### Quantitative execution through official DeerFlow

```bash
python adapters/deerflow_gateway.py run \
  --run-dir "$RUN_DIR" \
  --task-id quant-analysis \
  --agent quant-analysis-agent \
  --mode pro \
  --message-file "$RUN_DIR/tasks/quant-analysis/prompt.txt"
```

The quantitative agent must not have live web search or unvalidated data tools. Require point-in-time universe construction, corporate-action treatment, survivorship/revision/feature/label leakage controls, train-validation-test or walk-forward evaluation, costs, slippage, liquidity, capacity, multiple-testing controls, sensitivity, ablation, subperiod stability, and reproducible seeds.

Industry/company analysis must preserve source hierarchy, value-chain taxonomy, KPI comparability, observation-versus-publication timing, historical base rates, alternative causes, scenario assumptions, disconfirming indicators, and contradictions.

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

## 9. Reproduce material outputs

Regenerate material calculations, tables, and figures in a clean process. Record official DeerFlow version where relevant, Git commit, sandbox image digest, commands, seeds, input/output hashes, warnings, and differences in:

```text
runs/<run_id>/reproducibility_report.json
```

The report must contain `"status": "PASS"`:

```bash
python scripts/research_control.py checkpoint \
  --run-dir "$RUN_DIR" \
  --phase REPRODUCED
```

## 10. Run the release-data gate

```bash
python scripts/research_control.py gate \
  --run-dir "$RUN_DIR" \
  --stage release
```

This validates calculation lineage, claim references, contradiction status, and 100% support coverage for material claims. It preserves `release_data_gate_report.json` separately from acquisition validation.

## 11. Perform independent adversarial review

Start a genuinely separate Claude Code session or another approved reviewer outside the primary official DeerFlow run. Give it:

- research brief and approved plan;
- deployment preflight and data gate reports;
- source/dataset manifests;
- DeerFlow request/event/result audit records;
- code and relevant diff;
- calculation manifest and outputs;
- claim ledger;
- candidate charts/report.

Do not give it the implementer's private reasoning or tell it the work should pass.

An ACP Claude process spawned by the same primary DeerFlow run may help implementation, but does not independently authorize release.

The reviewer writes `runs/<run_id>/review_report.json`:

```json
{
  "status": "PASS",
  "critical_count": 0,
  "warning_count": 0,
  "findings": []
}
```

Then:

```bash
python scripts/research_control.py review --run-dir "$RUN_DIR"
```

If independent review is unavailable, stop with `NEEDS_HUMAN`.

## 12. Synthesize and release

Codex creates the candidate report using only verified claims and reproducible calculations. It also writes `release_requirements.json`:

```json
{
  "methodology_changed": false,
  "investment_recommendation": false,
  "material_source_conflict": false,
  "proxy_substitution_affects_conclusion": false,
  "human_approved": false
}
```

Any true sensitive flag requires `human_approved: true`.

```bash
python scripts/research_control.py release \
  --run-dir "$RUN_DIR" \
  --candidate candidate_report.md
```

Release rechecks:

1. DeerFlow deployment preflight;
2. acquisition and release-data gates;
3. reproducibility;
4. independent review with zero critical findings;
5. required human approval.

## 13. Hermes and OpenClaw

Hermes may retrieve approved operational knowledge and capture candidate lessons. Official DeerFlow memory and Hermes memory are never financial evidence.

OpenClaw may schedule runs, trigger intake, check heartbeat, and report terminal states. It may not alter Gate reports, waive failures, or publish conclusions.

## 14. Inspect current state

```bash
python scripts/research_control.py status --run-dir "$RUN_DIR"
```

Conversation history is not run state. `run_state.json` and preserved artifacts are the source of truth.

## Current production stop condition

Do not claim a real end-to-end financial run until the custom financial-data service provides its deployment/transport, authentication, dataset catalogue, field dictionary, entity mapping, units, revisions, adjustment conventions, point-in-time semantics, rate-limit/error behavior, licensing constraints, and representative market/fundamental/macro/filing/industry fixtures.
