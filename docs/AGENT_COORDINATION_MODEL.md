# Multi-Agent Coordination Model for Financial Research

This document defines how Codex, Claude Code, Hermes, OpenClaw, DeerFlow, and DeerFlow-style research executors should cooperate on finance research.

## Design goal

Build a research system that can produce rigorous, evidence-based financial analysis while preventing fabricated facts, unchecked data, look-ahead bias, and unsupported conclusions.

The system is organized as:

```text
OpenClaw / Hermes triggers
        ↓
Codex Chief Research Planner
        ↓
DeerFlow data/workflow services
        ↓
Specialist executors and reviewers
        ↓
Deterministic gates
        ↓
Research deliverable + evidence bundle
```

## Role assignment

### Codex: Chief Research Planner and Integration Lead

Codex owns:

- task qualification;
- research plan generation;
- repository changes;
- schema and contract updates;
- testable implementation tasks;
- evidence bundle assembly;
- final readiness summary;
- loop state updates.

Codex must not invent data or declare data valid without validation evidence.

### Claude Code: Deep Builder and Adversarial Reviewer

Claude Code owns:

- complex local refactors;
- debugging failed gates;
- reviewing methodology drift;
- challenging weak narratives;
- testing whether claims exceed evidence;
- reviewing chart/report rendering defects.

Claude Code is especially useful when the task requires long context over a codebase or careful diff review.

### Hermes: Memory, Skill, and Recurring Research Steward

Hermes owns:

- recurring schedules;
- long-running reminders;
- candidate skill capture;
- lessons-learned drafts;
- periodic research routines.

Hermes must store learnings as candidates first. It may not promote new rules directly into `AGENTS.md`, approved skills, or methodology files without review.

### OpenClaw: Always-on Operations Gateway

OpenClaw owns:

- standing orders;
- heartbeat checks;
- inbound task routing;
- webhook-triggered research or PR reviews;
- operational status visibility.

OpenClaw must not skip deterministic gates even for urgent tasks.

### DeerFlow: Data and Workflow Service Layer

DeerFlow owns:

- configured financial data retrieval;
- workflow execution;
- repeatable data pipelines;
- source adapter abstraction;
- raw and normalized dataset delivery.

Every DeerFlow output used in research must be accompanied by metadata and validation evidence.

### DeerFlow-style Research Executor

A research executor may perform:

- multi-step industry investigation;
- evidence collection;
- company/sector mapping;
- source triangulation;
- preliminary synthesis.

It must label facts, estimates, assumptions, and interpretations separately.

## Coordination states

```text
INTAKE
QUALIFIED
PLANNED
DATA_REQUESTED
DATA_RETRIEVED
DATA_VALIDATED
ANALYZED
REVIEWED
DELIVERED
RECORDED
BLOCKED
```

## Task routing matrix

| Task type | Planner | Executor | Reviewer | Required gate |
|---|---|---|---|---|
| Data adapter fix | Codex | Codex/Claude Code | Claude Code | data validation |
| Quant factor study | Codex | Codex + DeerFlow | Claude Code | leakage/backtest gates |
| Industry trend report | Codex | DeerFlow-style executor | Claude Code | source triangulation |
| Recurring market monitor | Hermes/OpenClaw | Codex + DeerFlow | Codex/Claude Code | freshness + source gates |
| PR review | Codex | Claude Code | Codex | diff + tests + methodology drift |
| Methodology update | Codex | Codex | Human/research owner | methodology approval |
| Report generation | Codex | Codex | Claude Code | consistency + rendering gates |

## Handoff contract

Every agent handoff must include:

```yaml
task_id: string
research_question: string
as_of_date: YYYY-MM-DD
allowed_sources: list
forbidden_sources: list
required_outputs: list
files_allowed_to_modify: list
validation_gates: list
known_risks: list
stop_conditions: list
```

## Codex planning template

Codex should write a plan before implementation:

```yaml
plan_id: string
objective: string
hypotheses:
  - id: H1
    statement: string
    evidence_required: list
    falsification_test: string
data_requests:
  - dataset: string
    source: deerflow
    fields: list
    frequency: string
    as_of_date: YYYY-MM-DD
validation_plan:
  - gate: source_identity
  - gate: freshness
  - gate: completeness
  - gate: unit_currency
  - gate: point_in_time
analysis_plan:
  - method: descriptive | backtest | event_study | cross_section | regression | scenario
review_plan:
  - reviewer: claude_code
  - reviewer: deterministic_gates
```

## Research evidence bundle

Each run should produce:

```text
runs/<run_id>/
├── task.yaml
├── plan.yaml
├── data_requests.yaml
├── data_validation.json
├── analysis_results.json
├── claims.yaml
├── review.md
├── gate_results.json
└── final_summary.md
```

## Claim ledger

Every research claim should be represented as:

```yaml
claim_id: C001
claim_type: fact | estimate | model_output | interpretation | recommendation
text: string
supporting_data:
  - dataset_id: string
    field: string
    observation_date: YYYY-MM-DD
supporting_sources:
  - source_name: string
    retrieved_at: ISO-8601 datetime
confidence: high | medium | low
limitations: list
review_status: pending | passed | failed
```

## Review standard

Reviewers should ask:

1. Is the source real and appropriate?
2. Is the data validated for this use case?
3. Is the as-of date respected?
4. Are units, currency, and frequencies consistent?
5. Are estimates labeled as estimates?
6. Does the conclusion overstate the evidence?
7. Is the methodology stable or explicitly changed?
8. Can another agent reproduce the result?
9. Are limitations visible in the main output?
10. Are any investment-like recommendations properly qualified?

## Learning loop

Lessons learned follow:

```text
incident or success
  ↓
candidate lesson
  ↓
candidate skill/rule
  ↓
regression replay
  ↓
review
  ↓
promotion
```

No agent may self-promote a candidate skill to an approved rule without review.
