# Multi-Agent Pipeline

An evidence-gated orchestration framework for financial and technical research across Codex, Claude Code, Hermes, deterministic validation, and supervised delivery.

## Project status

The only supported production runtime is under [`implementation/`](implementation/README.md). It uses one SQLite-backed state machine for ingress, leased execution, retries, typed artifact validation, report persistence, and exact-target notifications.

```text
Feishu -> Hermes ingress -> SQLite queue -> supervised worker
        -> QUALIFY -> ACQUIRE -> VALIDATE -> ANALYZE -> REVIEW -> DELIVER
        -> report.md + durable notification outbox
```

Removed v1 controllers, watchdogs, dispatchers, and parallel Hermes workflows are not supported and must not be restored.

## Repository map

| Path | Purpose | Production status |
|---|---|---|
| [`implementation/`](implementation/README.md) | Runtime, plugins, deployment, services, tests | **Production** |
| [`docs/`](docs/README.md) | Governance, architecture, project map, maintenance policy | Authoritative policy |
| [`schemas/`](schemas/) | Machine-readable research contracts | Authoritative contracts |
| [`loop/`](loop/) | Machine-readable research lifecycle | Authoritative workflow |
| [`examples/`](examples/README.md) | Demonstrations and historical patterns | Reference only |
| [`pipeline-template.js`](pipeline-template.js) | Earlier Claude Code Workflow pattern | Reference only |

See [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md) for ownership boundaries and rules for adding files or directories.

## Required reading for agents

Before starting, inspecting, recovering, deploying, or modifying the runtime, read:

1. [`AGENTS.md`](AGENTS.md)
2. [`docs/DATA_TRUST_CONTRACT.md`](docs/DATA_TRUST_CONTRACT.md)
3. [`implementation/docs/AGENT_USAGE_GUIDE.md`](implementation/docs/AGENT_USAGE_GUIDE.md)
4. [`implementation/docs/IMPLEMENTATION.md`](implementation/docs/IMPLEMENTATION.md)

## Common commands

The root [`Makefile`](Makefile) is the canonical command entry point:

```bash
make help
make test
make list
make status RUN_ID=<run_id>
make context RUN_ID=<run_id>
make retry RUN_ID=<run_id>
```

A blocked run should be retried only after correcting its underlying cause.

## Deployment

From the repository root on SZ81:

```bash
cd /home/ubuntu/multi-agent-pipeline
make deploy
```

The deployment process runs the test suite, installs and enables the HK43 Hermes plugin and helpers, installs the SZ81 worker/notifier timers, disables the removed watchdog units, and runs a cross-host health check.

Verify an installed environment with:

```bash
make health
```

Passing repository tests does not by itself prove HK43/SZ81 connectivity, agent authentication, provider availability, or Feishu delivery.

## Documentation

- [`docs/README.md`](docs/README.md) — repository documentation index
- [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md) — authoritative directory and ownership map
- [`docs/MAINTENANCE.md`](docs/MAINTENANCE.md) — change, migration, deprecation, and release policy
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — contribution workflow and PR requirements
- [`implementation/docs/README.md`](implementation/docs/README.md) — runtime documentation index
- [`implementation/docs/CURRENT_STATE.md`](implementation/docs/CURRENT_STATE.md) — current architecture and environment-dependent risks

## Research governance

The non-negotiable rule is that research must be based on validated facts and reproducible evidence. Agents must not fabricate data, sources, dates, prices, filings, calculations, or conclusions.

Repository-wide governance is defined by:

- [`AGENTS.md`](AGENTS.md)
- [`docs/DATA_TRUST_CONTRACT.md`](docs/DATA_TRUST_CONTRACT.md)
- [`docs/AGENT_COORDINATION_MODEL.md`](docs/AGENT_COORDINATION_MODEL.md)
- [`loop/research_loop.yaml`](loop/research_loop.yaml)
- [`schemas/task.schema.json`](schemas/task.schema.json)
- [`schemas/claim.schema.json`](schemas/claim.schema.json)

## Validation

```bash
make test
```

This compiles the Python modules, runs the unit and isolated integration suite, and validates deployment-shell syntax. GitHub Actions calls the same target to prevent local/CI command drift.
