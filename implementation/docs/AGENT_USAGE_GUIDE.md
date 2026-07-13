# Agent Usage Guide

This document is the operational contract for Codex, Claude Code, Hermes, OpenClaw, and any other agent working with the deployed multi-agent research runtime.

It explains how to start, observe, recover, review, and modify the pipeline without bypassing its evidence and safety gates.

## 1. Read order and precedence

Before acting in this repository, an agent must read:

1. `/AGENTS.md` — repository-wide research and change-management rules.
2. `/docs/DATA_TRUST_CONTRACT.md` — source, provenance, and validation requirements.
3. `/implementation/docs/AGENT_USAGE_GUIDE.md` — runtime operation instructions.
4. `/implementation/docs/IMPLEMENTATION.md` — deployment and host-level runbook.
5. `/implementation/README.md` — runtime overview and common commands.

If the documents conflict, use this precedence:

```text
AGENTS.md
  > DATA_TRUST_CONTRACT.md
  > AGENT_USAGE_GUIDE.md
  > IMPLEMENTATION.md
  > README.md
```

Never infer permission to bypass a hard gate from a lower-precedence document.

## 2. Supported runtime only

The only supported deployed runtime is:

```text
implementation/scripts/reliable_pipeline.py
```

The runtime path is:

```text
Feishu message
  -> Hermes pre_gateway_dispatch plugin on HK43
  -> reliable_ctl.py create on SZ81
  -> SQLite leased job queue
  -> systemd worker timer
  -> QUALIFY
  -> ACQUIRE
  -> VALIDATE
  -> ANALYZE
  -> REVIEW
  -> DELIVER
  -> report.md
  -> durable notification outbox
  -> exact Feishu conversation
```

Agents must not recreate or invoke the removed v1 file-state controller, old watchdog, old stage dispatcher, old trigger script, or a parallel native Hermes leaf workflow.

## 3. Agent responsibilities

### Codex

Codex is responsible for:

- qualifying the research request;
- producing the final report;
- planning repository changes;
- integrating fixes;
- running deterministic tests before claiming readiness.

Codex must not mark a run complete by editing SQLite or writing a fake stage artifact.

### Hermescold / Hermes research executor

Hermescold is responsible for:

- acquiring real source material and datasets;
- analyzing only validated evidence;
- returning structured stage artifacts;
- recording missing or inaccessible data as limitations.

Hermescold must not invent source access, fabricate observations, or convert unavailable data into confident estimates.

### Deterministic validator

The validator is responsible for:

- checking dataset identity;
- checking retrieval timestamps;
- checking that observations are present;
- rejecting unverified datasets;
- preventing invalid evidence from reaching analysis.

No model may override a failed validation result by narrative argument.

### Claude Code

Claude Code is responsible for adversarial review. It must check:

- whether claims are supported by acquired evidence;
- whether dates, units, currencies, and entities match;
- whether limitations are disclosed;
- whether the analysis overstates confidence;
- whether material evidence or alternative explanations are missing.

Claude Code must return `passed=false` when a material defect remains unresolved.

### OpenClaw or another operations agent

An operations agent may:

- receive and route requests;
- inspect task health;
- report blocked stages;
- invoke documented retry commands after the underlying issue is corrected;
- monitor services and notifications.

It must not bypass QUALIFY, VALIDATE, or REVIEW.

## 4. Starting a research run

### Preferred: Feishu

Send this exact trigger to the Hermes-connected Feishu conversation:

```text
启动多智能体研究：<research question>
```

Example:

```text
启动多智能体研究：分析未来十二个月美国 AI 数据中心融资风险，要求区分利率风险、信用利差风险和项目现金流风险，并列明数据截止日期。
```

The ingress plugin must:

1. create one durable run on SZ81;
2. record the exact Feishu target;
3. return `skip` to stop the native Hermes workflow;
4. acknowledge the new `run_id`.

Do not send the same request through a second agent after the durable run has been created.

### Manual CLI creation on SZ81

From the repository root:

```bash
export PIPELINE_DB=/home/ubuntu/multi-agent-pipeline/implementation/state/pipeline.db
export PIPELINE_RUNS_DIR=/home/ubuntu/multi-agent-pipeline/implementation/state/runs

printf '%s' '<research question>' | python3 implementation/scripts/reliable_ctl.py \
  --db "$PIPELINE_DB" \
  --runs-dir "$PIPELINE_RUNS_DIR" \
  create \
  --question-stdin \
  --requester manual
```

Save the returned `run_id`. Never generate a run directory or database row manually.

## 5. Observing a run

### List recent runs

```bash
python3 implementation/scripts/reliable_ctl.py \
  --db "$PIPELINE_DB" \
  --runs-dir "$PIPELINE_RUNS_DIR" \
  list --limit 20
```

### Inspect status

```bash
python3 implementation/scripts/reliable_ctl.py \
  --db "$PIPELINE_DB" \
  --runs-dir "$PIPELINE_RUNS_DIR" \
  status <run_id>
```

Check:

- `run.status`;
- `run.stage`;
- `run.last_error`;
- job `status`, `attempts`, `worker_id`, and `lease_until`;
- artifact `valid` flags.

### Inspect the context sent to the next agent

```bash
python3 implementation/scripts/reliable_ctl.py \
  --db "$PIPELINE_DB" \
  --runs-dir "$PIPELINE_RUNS_DIR" \
  context <run_id>
```

Use this command when diagnosing whether the research question or prior artifacts are missing.

### Inspect persisted files

```text
implementation/state/runs/<run_id>/status.json
implementation/state/runs/<run_id>/raw/<stage>.txt
implementation/state/runs/<run_id>/artifacts/<stage>.json
implementation/state/runs/<run_id>/report.md
```

Raw responses are evidence. Do not delete or rewrite them merely to make a failed stage pass.

## 6. Stage contracts

Every model stage must return one JSON object containing `stage` plus the required fields below.

### QUALIFY

```json
{
  "stage": "QUALIFY",
  "qualified": true,
  "research_question": "...",
  "scope": [],
  "risks": [],
  "evidence": []
}
```

Set `qualified=false` when material ambiguity prevents safe research.

### ACQUIRE

```json
{
  "stage": "ACQUIRE",
  "datasets": [],
  "limitations": [],
  "evidence": []
}
```

Each usable dataset should identify at least:

- `dataset_id`;
- `source_name`;
- `source_ref` or `url`;
- `retrieved_at`;
- `observations`, `data`, or `facts`;
- `validation_status`.

### VALIDATE

```json
{
  "stage": "VALIDATE",
  "overall_pass": true,
  "checks": [],
  "limitations": [],
  "evidence": []
}
```

This stage is deterministic. An unverified or structurally incomplete dataset must fail.

### ANALYZE

```json
{
  "stage": "ANALYZE",
  "claims": [],
  "methodology": "...",
  "limitations": [],
  "evidence": []
}
```

Each claim should separate the claim, evidence references, confidence, and reasoning.

### REVIEW

```json
{
  "stage": "REVIEW",
  "passed": true,
  "findings": [],
  "evidence": []
}
```

`passed=true` is allowed only when no unresolved material finding remains.

### DELIVER

```json
{
  "stage": "DELIVER",
  "executive_summary": "...",
  "report_markdown": "# Report\n...",
  "evidence": []
}
```

The final report must include findings, evidence references, limitations, and the relevant as-of date.

The controller tolerates a short preface or fenced JSON, but one valid JSON object is mandatory.

## 7. Understanding normal states

```text
ACTIVE   The current stage is waiting, leased, or retrying.
DONE     All six stages passed and report.md was persisted.
BLOCKED  A hard gate failed or the retry budget was exhausted.
FAILED   Reserved for unrecoverable controller-level failure.
```

A blocked run is not a broken system by itself. It may be the correct result when evidence is unavailable or invalid.

## 8. Recovering a blocked run

First diagnose and correct the cause. Common examples:

- agent command or authentication failure;
- SSH alias failure;
- inaccessible data source;
- malformed agent output;
- failed deterministic validation;
- failed independent review;
- expired worker lease after a host interruption.

After correcting the cause, retry the current stage:

```bash
python3 implementation/scripts/reliable_ctl.py \
  --db "$PIPELINE_DB" \
  --runs-dir "$PIPELINE_RUNS_DIR" \
  retry <run_id>
```

Do not retry repeatedly without changing the underlying condition. Do not reset attempts with direct SQL.

## 9. Service and deployment checks

Run on SZ81:

```bash
implementation/deploy/healthcheck.sh
```

Relevant services:

```bash
systemctl status multi-agent-pipeline-worker.timer
systemctl status multi-agent-pipeline-worker.service
systemctl status multi-agent-pipeline-notify.timer
systemctl status multi-agent-pipeline-notify.service
```

Useful logs:

```bash
journalctl -u multi-agent-pipeline-worker.service -n 200 --no-pager
journalctl -u multi-agent-pipeline-notify.service -n 200 --no-pager
```

Full deployment from SZ81:

```bash
cd /home/ubuntu/multi-agent-pipeline
implementation/deploy/deploy-all.sh
```

The deployment script runs tests, installs controller services, installs and enables the Hermes plugin on HK43, removes old watchdog units, and runs a cross-host health check.

## 10. Rules for coding agents modifying the runtime

Before changing code:

1. identify whether the change affects ingress, state, execution, validation, review, persistence, notification, or deployment;
2. preserve one SQLite state machine;
3. preserve raw model output;
4. preserve idempotent request creation;
5. preserve leased atomic job claiming;
6. preserve hard gates;
7. preserve exact-target notifications;
8. preserve legacy database migration unless an explicit destructive migration is approved.

After changing code, run:

```bash
python3 -m compileall -q implementation/scripts implementation/plugins implementation/tests
python3 -m unittest discover -s implementation/tests -v
bash -n implementation/deploy/*.sh
```

A runtime PR is not merge-ready unless it includes:

- root cause;
- files changed;
- behavioral impact;
- migration impact;
- tests run;
- deployment impact;
- remaining environment-dependent risks.

## 11. Prohibited actions

Agents must not:

- restore or call the removed v1 controller or watchdog;
- create a second queue or state machine;
- edit SQLite rows to force `DONE`;
- write stage artifacts directly to skip model execution;
- discard raw responses after parser failure;
- treat `unverified` data as validated;
- change `overall_pass=false` or `passed=false` to true without correcting the evidence;
- run the native Hermes leaf workflow in parallel with the durable trigger;
- claim live deployment success based only on unit tests;
- claim research completion when `report.md` does not exist for a `DONE` run.

## 12. Definition of done

A research run is complete only when all of the following are true:

```text
run.status == DONE
all stage jobs == SUCCEEDED
all stage artifacts are valid
QUALIFY.qualified == true
VALIDATE.overall_pass == true
REVIEW.passed == true
state/runs/<run_id>/report.md exists
completion notification is either sent or remains durably pending
```

A code change is complete only when:

```text
repository tests pass
GitHub Actions pass
runtime documentation matches behavior
migration impact is documented
no legacy execution path is reintroduced
live host deployment is separately verified or explicitly marked unverified
```

## 13. Minimal agent handoff format

When one agent hands this project to another, use:

```text
Repository: kevinsutianxing/multi-agent-pipeline
Runtime: implementation/ SQLite pipeline only
Branch/PR: <branch or PR>
Task: <exact task>
Current run_id: <run_id or none>
Current stage/status: <stage/status>
Evidence inspected: <paths, logs, commands>
Changes made: <files>
Validation run: <commands and results>
Remaining environment checks: <HK43/SZ81/auth/data access>
Do not use: removed v1 controller/watchdog/native parallel Hermes flow
Next action: <one concrete action>
```
