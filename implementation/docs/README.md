# Runtime Documentation Index

This directory documents the only supported production runtime in the repository.

## Read order

1. [`AGENT_USAGE_GUIDE.md`](AGENT_USAGE_GUIDE.md) — mandatory operating contract for agents and operators.
2. [`IMPLEMENTATION.md`](IMPLEMENTATION.md) — deployment, service, and host-level runbook.
3. [`CURRENT_STATE.md`](CURRENT_STATE.md) — current architecture, resolved root causes, and environment-dependent risks.
4. [`../README.md`](../README.md) — concise runtime overview and common commands.

Repository-wide policy is defined by:

- [`../../AGENTS.md`](../../AGENTS.md)
- [`../../docs/DATA_TRUST_CONTRACT.md`](../../docs/DATA_TRUST_CONTRACT.md)
- [`../../docs/PROJECT_MAP.md`](../../docs/PROJECT_MAP.md)
- [`../../docs/MAINTENANCE.md`](../../docs/MAINTENANCE.md)

## Authority and precedence

```text
AGENTS.md
  > DATA_TRUST_CONTRACT.md
  > AGENT_USAGE_GUIDE.md
  > IMPLEMENTATION.md
  > CURRENT_STATE.md
  > README.md
```

Code and tests remain the source of truth for actual behavior. When documentation and behavior differ, block deployment, fix the inconsistency, and update the authoritative document in the same pull request.

## Runtime boundary

Production components belong under `implementation/`:

- `scripts/` — controller, worker, adapters, notification sender, and operator CLI;
- `plugins/` — Hermes ingress integration;
- `deploy/` — installation and health-check scripts;
- `systemd/` — supervised worker and notifier units;
- `tests/` — unit and isolated integration tests;
- `state/` — local generated state, excluded from Git.

Do not add production scripts, daemons, state machines, or deployment entry points elsewhere in the repository.
