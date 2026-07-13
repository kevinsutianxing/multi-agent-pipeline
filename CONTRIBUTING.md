# Contributing

This repository combines a production orchestration runtime with financial-research governance. Changes must preserve both operational reliability and evidence integrity.

## Before changing anything

Read, in order:

1. [`AGENTS.md`](AGENTS.md)
2. [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md)
3. [`docs/MAINTENANCE.md`](docs/MAINTENANCE.md)
4. [`implementation/docs/AGENT_USAGE_GUIDE.md`](implementation/docs/AGENT_USAGE_GUIDE.md) for runtime work
5. [`docs/DATA_TRUST_CONTRACT.md`](docs/DATA_TRUST_CONTRACT.md) for research or data work

## Branch and scope

Use a focused branch such as:

```text
agent/<short-description>
fix/<short-description>
docs/<short-description>
```

Keep one primary change class per pull request. Do not combine unrelated runtime, methodology, and formatting changes.

## Canonical checks

Run the same validation used by CI:

```bash
make test
```

For deployment or host-integration changes, also run on SZ81:

```bash
make health
```

Environment-dependent checks must be reported separately from isolated tests.

## Runtime rules

Runtime changes must:

- stay under `implementation/`;
- preserve the single SQLite-backed execution path;
- preserve raw model output and validated artifacts;
- preserve idempotent creation, atomic leases, retries, hard gates, and exact-target notifications;
- include migration handling for existing databases and runs;
- update tests and the authoritative runtime documentation.

Do not restore removed v1 components or add another scheduler, queue, watchdog, trigger, or controller.

## Research and data rules

Research changes must:

- record source identity, retrieval time, observation time, units, transformations, and validation state;
- separate facts, calculations, inferences, assumptions, and limitations;
- prevent look-ahead leakage and unsupported conclusions;
- receive independent review before changing methodology, scoring, accepted sources, risk labels, or investment recommendations.

## Pull-request checklist

A complete PR explains:

- the root cause or motivation;
- what changed and what did not change;
- files and systems affected;
- behavior before and after;
- data-source and methodology impact;
- migration and deployment impact;
- tests and validation performed;
- remaining risks and environment checks;
- reviewer result.

Do not claim production deployment merely because CI passed. Do not claim research completion without validated evidence and a persisted final report.
