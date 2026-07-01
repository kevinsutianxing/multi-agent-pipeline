# Runtime Adapter Guide

The research protocol is platform-neutral. Each runtime is an adapter around the same task envelope, artifact paths, and deterministic gates.

## Codex

Use Codex as Chief Research Planner and Integrator. It should load root `AGENTS.md`, create a run directory, emit a schema-valid plan, and execute one bounded task attempt at a time.

Suggested non-interactive pattern:

```bash
codex exec \
  --sandbox workspace-write \
  --output-schema schemas/task-result.schema.json \
  -o runs/$RUN_ID/tasks/$TASK_ID/result.json \
  "Read AGENTS.md and execute task envelope runs/$RUN_ID/tasks/$TASK_ID/task.json"
```

The outer controller runs acceptance commands and decides retries. Codex prose must not be treated as a gate result.

## Claude Code

Use Claude Code as an independent adversarial reviewer and for complex implementation/debugging tasks. The reviewer receives the brief, approved plan, manifests, code diff, deterministic gate reports, calculation artifacts, claim ledger, and candidate report.

Do not give the reviewer the implementer's private reasoning or instruct it that the result is expected to pass. A same-session self-review is not independent review.

## DeerFlow Data Service

Implement HTTP, MCP, CLI, or SDK transport behind this logical operation:

```text
acquire(request.json)
  -> raw snapshots
  -> source_manifest.data.json
  -> dataset_manifest.json
  -> retrieval diagnostics
```

Required behavior:

- bounded query scope;
- credentials redacted from manifests;
- immutable raw snapshots;
- provider response metadata and timestamps;
- explicit publication/availability rules;
- stable identifiers, units, currency, timezone, frequency, and adjustment conventions;
- no self-certification.

## DeerFlow Research Agent

Use for broad industry evidence collection. It writes `source_manifest.research.json`, emphasizing filings, official statistics, issuer disclosures, regulators, and exchanges before secondary commentary.

Keep this logical role distinct from the data service, even when they share infrastructure. A research agent must not be treated as the source of record for data it interpreted.

## Hermes

At task start, Hermes may retrieve approved skills and source notes. New observations go only to candidate memory/skill directories until regression-tested and approved.

A new cron/session must recover from `run_state.json`; conversational memory is not run state.

## OpenClaw

Use cron, webhooks, and heartbeat for:

- creating intake tasks;
- checking stalled runs;
- triggering scheduled data refreshes;
- reporting terminal-state transitions;
- surfacing external-source outages.

OpenClaw must not alter gate reports, waive failures, or publish financial conclusions.

## DeerFlow naming ambiguity

Some installations use the name DeerFlow for both an agent framework and a financial-data service. Use separate adapter identifiers:

```text
deerflow-data
deerflow-research
```

This preserves responsibility separation and prevents self-certification.
