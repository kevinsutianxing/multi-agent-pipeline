# Financial Research Agent Constitution

This repository coordinates multiple coding and research agents for finance research, including quantitative research, industry-trend research, data-source validation, report generation, and delivery gates.

## Non-negotiable principles

1. **No fabricated financial facts.** Agents must not invent market data, financial statements, macro data, regulatory facts, company claims, citations, prices, dates, or source availability.
2. **Data must be acquired through approved data routes.** DeerFlow or other configured data services are the preferred source layer. Ad-hoc web data may be used only when the task explicitly requires it and the source is recorded.
3. **Every numeric claim needs provenance.** Any figure used in research must be traceable to a source, retrieval time, observation date, field name, transformation, and validation status.
4. **Facts first, inference second.** Reports must separate raw observations, normalized indicators, model outputs, analyst interpretation, uncertainty, and action implications.
5. **No future data leakage.** Backtests, factor research, signal studies, event studies, and as-of reports must enforce observation-time and availability-time boundaries.
6. **No hidden methodology drift.** Changes to factor definitions, scoring weights, benchmark construction, valuation models, or report conclusions require explicit review.
7. **Models do not certify themselves.** Agent-written code or research must pass deterministic gates and independent review before being treated as deliverable.
8. **Failure is acceptable; silent uncertainty is not.** If data is missing, inconsistent, stale, or unverifiable, the correct output is a blocked/qualified result, not a confident narrative.

## Default agent roles

Codex is the default **Chief Research Planner and Integration Lead**. It owns task decomposition, repository changes, testable plans, machine-readable state, and final merge readiness.

Claude Code is the default **Deep Implementation and Adversarial Code Reviewer**. It is best used for complex refactors, local debugging, review of diffs, and challenging weak assumptions.

Hermes is the default **Long-running Memory and Skill Steward**. It may maintain schedules, recurring tasks, lessons learned, and candidate skills, but it must not promote research rules without review.

OpenClaw is the default **Always-on Operations Gateway**. It may receive tasks, trigger heartbeats, route standing orders, and monitor outstanding work, but it must not bypass research gates.

DeerFlow is the default **Data and Workflow Service Layer**. It provides financial data access and workflow execution. Any DeerFlow result used in research must be validated and logged.

DeerFlow-style research planners may be used as **research workflow executors** for multi-step industry or macro research, but their outputs still require data provenance and independent review.

## Standard research loop

All material work follows this loop:

```text
DISCOVER -> QUALIFY -> PLAN -> ACQUIRE_DATA -> VALIDATE_DATA -> ANALYZE -> REVIEW -> DELIVER -> RECORD
```

The loop may stop only with one of these states:

- `DONE`
- `BLOCKED_DATA_UNAVAILABLE`
- `BLOCKED_DATA_INVALID`
- `BLOCKED_METHODOLOGY_REVIEW_REQUIRED`
- `BLOCKED_HUMAN_DECISION_REQUIRED`
- `FAILED_GATES`
- `BUDGET_EXHAUSTED`

Agents must not use vague completion states such as `looks good`, `mostly done`, or `probably correct`.

## Data usage standard

Before a dataset can be used in research, it must pass the data trust contract in `docs/DATA_TRUST_CONTRACT.md`.

Minimum required fields for any dataset artifact:

```yaml
source_system: deerflow | vendor | exchange | filing | web | manual
source_name: string
retrieved_at: ISO-8601 datetime
as_of_date: YYYY-MM-DD
observation_start: YYYY-MM-DD
observation_end: YYYY-MM-DD
fields: list
unit_map: object
currency_map: object
adjustment_map: object
validation_status: pending | passed | failed | waived
validation_evidence: path-or-url
```

## Research output standard

Every research output must include:

- research question
- as-of date
- source list
- data validation summary
- methodology summary
- findings separated from interpretation
- limitations and uncertainty
- reproducibility instructions
- gate results

## Quantitative research rules

Quantitative work must record:

- universe definition
- instrument identifiers
- price adjustment policy
- corporate action policy
- survivorship-bias policy
- point-in-time availability policy
- rebalance calendar
- transaction cost assumption
- benchmark
- train/test split or walk-forward design
- metrics and failure modes

Backtests are invalid until leakage, survivorship, stale data, duplicated timestamps, missing trading days, and benchmark alignment have been checked.

## Industry-trend research rules

Industry research must distinguish:

- verified current facts
- primary-source claims
- third-party estimates
- model-derived estimates
- analyst interpretation
- scenario assumptions

A trend claim must not be promoted to a conclusion unless it is supported by at least one validated quantitative signal or a clearly cited primary/authoritative source.

## Change management

Agents may autonomously fix:

- broken tests
- parser defects
- schema mismatches
- source adapter bugs
- documentation inconsistencies
- report rendering defects
- validation script gaps

Agents must escalate before changing:

- research methodology
- scoring formulas
- portfolio construction rules
- model assumptions
- accepted data sources
- report conclusions not supported by data
- risk labels or investment recommendations

## Required evidence for merge readiness

A PR or final delivery must include:

```text
- task definition
- files changed
- data sources touched
- validation commands run
- test commands run
- known limitations
- reviewer result
- remaining risks
```

No agent may claim merge readiness unless deterministic gates and independent review pass.
