# Documentation Index

This directory contains repository-wide governance, architecture, and research-method documents. Runtime-specific operating material lives under [`implementation/docs/`](../implementation/docs/README.md).

## Start here

1. [`../README.md`](../README.md) — project purpose and supported deployment.
2. [`../AGENTS.md`](../AGENTS.md) — mandatory rules for coding and research agents.
3. [`PROJECT_MAP.md`](PROJECT_MAP.md) — authoritative repository layout and ownership boundaries.
4. [`../implementation/docs/AGENT_USAGE_GUIDE.md`](../implementation/docs/AGENT_USAGE_GUIDE.md) — how to start, observe, recover, deploy, and modify the production runtime.

## Governance

- [`DATA_TRUST_CONTRACT.md`](DATA_TRUST_CONTRACT.md) — provenance, validation, and data acceptance rules.
- [`AGENT_COORDINATION_MODEL.md`](AGENT_COORDINATION_MODEL.md) — default agent roles and coordination model.
- [`MAINTENANCE.md`](MAINTENANCE.md) — repository hygiene, change classes, release discipline, and deprecation rules.
- [`../loop/research_loop.yaml`](../loop/research_loop.yaml) — machine-readable research lifecycle.
- [`../schemas/`](../schemas/) — machine-readable task and claim contracts.

## Runtime operations

- [`../implementation/README.md`](../implementation/README.md) — runtime overview and common commands.
- [`../implementation/docs/README.md`](../implementation/docs/README.md) — runtime documentation index.
- [`../implementation/docs/IMPLEMENTATION.md`](../implementation/docs/IMPLEMENTATION.md) — deployment and host runbook.
- [`../implementation/docs/CURRENT_STATE.md`](../implementation/docs/CURRENT_STATE.md) — current architecture and known environment-dependent risks.

## Reference material

- [`../examples/`](../examples/) and [`../pipeline-template.js`](../pipeline-template.js) are reference examples only.
- They are not part of the deployed runtime and must not introduce an alternative queue, state machine, daemon, trigger, or delivery path.

## Documentation rule

Prefer linking to the authoritative document instead of copying commands or policies into another file. When behavior changes, update code, tests, the authoritative runtime document, and the project map in the same pull request.
