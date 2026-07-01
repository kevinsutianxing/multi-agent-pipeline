# Codex-Led Financial Research Runbook

This runbook turns the repository governance documents into an operational workflow. Codex plans and integrates; DeerFlow acquires data and evidence; deterministic scripts decide data validity; Claude Code performs independent review; Hermes and OpenClaw support memory and operations without deciding research truth.

## 1. Start a run

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

## 2. Ask Codex to plan

Start Codex with `prompts/CODEX_CHIEF_RESEARCH_PLANNER.md`. It must read the repository governance files and create:

```text
runs/<run_id>/research_plan.json
runs/<run_id>/tasks/<task_id>/task.json
```

The plan must conform to `schemas/research-plan.schema.json`. It must preregister hypotheses, disconfirming evidence, data requirements, task dependencies, artifact contracts, acceptance commands, retry limits, and human-approval items.

After reviewing the plan artifact:

```bash
python scripts/research_control.py checkpoint \
  --run-dir "$RUN_DIR" \
  --phase PLANNED
```

## 3. Acquire data and research evidence

Run two logical DeerFlow adapters, even when both are implemented by the same deployment.

### DeerFlow data adapter

Input: bounded requests from `research_plan.json`.

Required outputs:

```text
runs/<run_id>/raw/...
runs/<run_id>/source_manifest.data.json
runs/<run_id>/dataset_manifest.json
```

### DeerFlow research adapter

Input: source hierarchy and evidence requests from `research_plan.json`.

Required output:

```text
runs/<run_id>/source_manifest.research.json
```

It should prioritize filings, regulators, exchanges, official statistics, and issuer disclosures. Secondary commentary must remain labeled as secondary evidence.

After both adapters finish:

```bash
python scripts/research_control.py checkpoint \
  --run-dir "$RUN_DIR" \
  --phase ACQUIRED
```

## 4. Run the acquisition gate

```bash
python scripts/research_control.py gate \
  --run-dir "$RUN_DIR" \
  --stage acquisition
```

The controller runs the manifest merger and deterministic evidence validator. A successful API response or an agent's `overall_pass=true` is not sufficient.

A passing run moves to `DATA_VALIDATED`. A critical failure moves to `BLOCKED_DATA` and preserves `acquisition_gate_report.json`.

## 5. Execute quantitative and/or industry research

Codex assigns bounded specialist tasks only after `DATA_VALIDATED`.

### Quantitative track

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

### Industry/company track

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

## 6. Reproduce material outputs

Regenerate material calculations, tables, and figures in a clean process. Record the environment, git commit, command, seeds, input hashes, output hashes, warnings, and differences in:

```text
runs/<run_id>/reproducibility_report.json
```

The report must contain `"status": "PASS"` before the controller accepts it:

```bash
python scripts/research_control.py checkpoint \
  --run-dir "$RUN_DIR" \
  --phase REPRODUCED
```

## 7. Run the release-data gate

```bash
python scripts/research_control.py gate \
  --run-dir "$RUN_DIR" \
  --stage release
```

This validates calculation lineage, claim references, contradiction status, and 100% support coverage for material claims. The report is stored separately as `release_data_gate_report.json`.

## 8. Perform independent adversarial review

Start a genuinely separate Claude Code session or another approved reviewer. Give it:

- research brief and approved plan;
- source and dataset manifests;
- acquisition and release-data gate reports;
- code and relevant diff;
- calculation manifest and outputs;
- claim ledger;
- candidate charts/report if available.

Do not give it the implementer's private reasoning and do not instruct it that the work should pass.

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

## 9. Synthesize and release

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

## 10. Hermes and OpenClaw integration

### Hermes

Use Hermes to retrieve approved source quirks and procedures before planning, and to write post-run lessons only under candidate memory/skill paths. Promotion requires regression evidence and independent approval.

### OpenClaw

Use OpenClaw for schedules, webhooks, heartbeat checks, and notifications. It may create intake tasks and report terminal states. It must not alter gate reports, waive failures, or publish research conclusions.

## 11. Inspect current state

```bash
python scripts/research_control.py status --run-dir "$RUN_DIR"
```

The conversation history of an agent is not run state. `run_state.json` and preserved artifacts are the source of truth.
