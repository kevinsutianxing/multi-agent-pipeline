# Multi-Agent Pipeline

An evidence-gated orchestration framework for financial and technical research
across Codex, Claude Code, Hermes, and deterministic validation steps.

## Supported deployment

The only supported production runtime is under [`implementation/`](implementation/README.md).
It uses one SQLite-backed state machine for ingress, leased execution, retries,
artifact validation, report persistence, and exact-target notifications.

Agents must follow [`implementation/docs/AGENT_USAGE_GUIDE.md`](implementation/docs/AGENT_USAGE_GUIDE.md) before starting, inspecting, recovering, deploying, or modifying the runtime.

```text
Feishu -> Hermes ingress -> SQLite queue -> supervised worker
        -> QUALIFY -> ACQUIRE -> VALIDATE -> ANALYZE -> REVIEW -> DELIVER
        -> report.md + durable notification outbox
```

Deploy from SZ81:

```bash
cd /home/ubuntu/multi-agent-pipeline
implementation/deploy/deploy-all.sh
```

The deployment script runs the test suite, installs/enables the HK43 Hermes
plugin and helpers, installs the SZ81 worker/notifier timers, disables the old
watchdog, and runs a cross-host health check.

See:

- [`implementation/docs/AGENT_USAGE_GUIDE.md`](implementation/docs/AGENT_USAGE_GUIDE.md) — required operating instructions for agents
- [`implementation/README.md`](implementation/README.md) — runtime overview and commands
- [`implementation/docs/IMPLEMENTATION.md`](implementation/docs/IMPLEMENTATION.md) — deployment/runbook
- [`implementation/docs/CURRENT_STATE.md`](implementation/docs/CURRENT_STATE.md) — resolved root causes and validation

## Research governance

The repository-level finance overlay remains governed by:

- [`AGENTS.md`](AGENTS.md)
- [`docs/DATA_TRUST_CONTRACT.md`](docs/DATA_TRUST_CONTRACT.md)
- [`docs/AGENT_COORDINATION_MODEL.md`](docs/AGENT_COORDINATION_MODEL.md)
- [`loop/research_loop.yaml`](loop/research_loop.yaml)
- [`schemas/task.schema.json`](schemas/task.schema.json)
- [`schemas/claim.schema.json`](schemas/claim.schema.json)

The non-negotiable rule is that research must be based on validated facts and
reproducible evidence. Agents must not fabricate data, sources, dates, prices,
filings, calculations, or conclusions.

## Reference templates

`pipeline-template.js` and `examples/` are retained as reference patterns for
Claude Code Workflow/`cc-connect`. They are not the deployed runtime and should
not be mixed with the services under `implementation/`.

## Tests

```bash
python3 -m compileall -q implementation/scripts implementation/plugins implementation/tests
python3 -m unittest discover -s implementation/tests -v
bash -n implementation/deploy/*.sh
```
