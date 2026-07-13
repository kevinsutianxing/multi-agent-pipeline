# Reliable Multi-Agent Research Runtime

This directory contains the repository's only supported deployable runtime. The earlier file-state controller and watchdog were removed because they created a second, disconnected execution path.

Agents operating or modifying this runtime must first read:

1. [`docs/README.md`](docs/README.md) — runtime documentation index.
2. [`docs/AGENT_USAGE_GUIDE.md`](docs/AGENT_USAGE_GUIDE.md) — supported commands, stage contracts, recovery rules, and definition of done.
3. [`docs/IMPLEMENTATION.md`](docs/IMPLEMENTATION.md) — deployment and host runbook.

## Runtime

```text
Feishu -> Hermes pre_gateway_dispatch plugin (HK43)
       -> reliable_ctl create (SZ81)
       -> SQLite leased job queue
       -> systemd worker timer
       -> QUALIFY -> ACQUIRE -> VALIDATE -> ANALYZE -> REVIEW -> DELIVER
       -> state/runs/<run_id>/report.md
       -> durable notification outbox -> exact Feishu conversation
```

The controller preserves every raw model response before normalization. A job advances only after its typed stage contract passes. QUALIFY, VALIDATE, and REVIEW are hard gates.

## Directory ownership

- `scripts/` — controller, worker, adapters, operator CLI, and notification sender.
- `plugins/` — Hermes ingress integration.
- `deploy/` — installation and health checks.
- `systemd/` — supervised worker and notification units.
- `tests/` — unit and isolated integration tests.
- `docs/` — authoritative runtime operation and deployment documentation.
- `state/` — generated local state; never commit it.

## Deploy

From the repository root on SZ81:

```bash
make deploy
```

Configuration is installed at `/etc/multi-agent-pipeline.env`. Review `implementation/config/pipeline.env.example` before production use, especially SSH aliases and agent commands.

## Verify

```bash
make health
make list
```

Create a manual smoke task directly through the operator CLI:

```bash
printf '%s' '研究任务' | python3 implementation/scripts/reliable_ctl.py \
  --db implementation/state/pipeline.db \
  --runs-dir implementation/state/runs \
  create --question-stdin --requester manual
```

## Services

- `multi-agent-pipeline-worker.timer`: leases and executes one stage at a time.
- `multi-agent-pipeline-notify.timer`: flushes the durable notification outbox.
- `reliable_research_ingress`: Hermes plugin that intercepts the exact `启动多智能体研究：...` trigger and returns `skip` so the native leaf workflow cannot run in parallel.

## Tests

From the repository root:

```bash
make test
```

GitHub Actions invokes the same target so local validation and CI do not drift.
