# Project Map

This file is the authoritative map of the repository. It exists to prevent agents and maintainers from creating duplicate runtimes, duplicate policies, or ambiguous entry points.

## Repository layout

```text
multi-agent-pipeline/
├── README.md                     Human entry point and deployment summary
├── AGENTS.md                     Mandatory agent constitution
├── CONTRIBUTING.md               Change workflow and pull-request requirements
├── Makefile                      Canonical local validation and operator shortcuts
├── docs/                         Repository-wide governance and architecture
├── schemas/                      Machine-readable research contracts
├── loop/                         Machine-readable research lifecycle
├── implementation/               Only supported production runtime
├── examples/                     Non-production reference examples
├── pipeline-template.js          Legacy/reference workflow template
└── .github/                      CI and pull-request policy
```

## Ownership boundaries

| Area | Status | Purpose | Changes belong here |
|---|---|---|---|
| `implementation/` | Production | SQLite state machine, agents, plugins, deployment, tests | Runtime and operations code |
| `docs/` | Authoritative governance | Data trust, coordination, maintenance, architecture | Cross-cutting policy and design |
| `schemas/` | Authoritative contracts | Task, claim, and other machine-readable schemas | Contract changes with compatibility review |
| `loop/` | Authoritative workflow | Research lifecycle and gate ordering | Lifecycle changes with methodology review |
| `examples/` | Reference only | Demonstrations and historical patterns | Examples that do not execute in production |
| `pipeline-template.js` | Reference only | Earlier Claude Code Workflow pattern | Compatibility/reference maintenance only |
| `.github/` | Repository automation | CI and PR templates | Checks and contribution automation |

## Production runtime

The only supported deployed execution path is:

```text
Feishu
  -> Hermes pre_gateway_dispatch plugin on HK43
  -> reliable_ctl create on SZ81
  -> SQLite leased job queue
  -> worker timer
  -> QUALIFY -> ACQUIRE -> VALIDATE -> ANALYZE -> REVIEW -> DELIVER
  -> report.md
  -> durable exact-target notification outbox
```

Authoritative runtime code and operating documents are under `implementation/`.

## Where to make a change

- Change stage behavior or contracts: `implementation/scripts/`, tests, and runtime docs.
- Change deployment or services: `implementation/deploy/`, `implementation/systemd/`, health checks, and runbook.
- Change agent ingress: `implementation/plugins/` plus ingress integration tests.
- Change data acceptance policy: `docs/DATA_TRUST_CONTRACT.md` and relevant schemas/tests.
- Change agent responsibilities: `AGENTS.md` and `docs/AGENT_COORDINATION_MODEL.md`.
- Add a non-production example: `examples/`, with an explicit reference-only notice.
- Add an operator shortcut: `Makefile`; do not create an undocumented root shell script.

## Prohibited structure drift

Do not:

- add another controller, queue, database, watchdog, dispatcher, or daemon outside `implementation/`;
- put production scripts in the repository root;
- duplicate runtime commands across multiple documents without declaring one authoritative source;
- treat files under `examples/` or `pipeline-template.js` as deployed components;
- create direct database mutation tools that bypass `reliable_ctl.py`;
- add generated state, reports, secrets, local databases, caches, or credentials to Git.

## Adding a new top-level directory

A new top-level directory requires all of the following in the same pull request:

1. a clear owner and purpose;
2. an explanation of why an existing directory is insufficient;
3. an update to this project map;
4. tests or validation where applicable;
5. confirmation that it does not create a second production path.
