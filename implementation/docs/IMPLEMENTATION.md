# Implementation and Operations

## Root cause fixed

The previous deployment mixed two controllers:

- Feishu ingress created a SQLite v2 job.
- The installed watchdog invoked the unrelated v1 file-state controller.
- No supervised v2 worker or notifier consumed the SQLite queue.
- Repository files lived under `implementation/`, while services referenced paths without that directory.
- Workers received a stage name but not the research question or prior artifacts.
- Agent stdout had to be pure JSON, so normal model prefaces and Markdown fences caused retries and blocking.

The runtime now has one owner of state and one execution path.

## State and evidence

SQLite is the canonical state store. A human-readable mirror is written to:

```text
implementation/state/runs/<run_id>/
  status.json
  raw/<stage>.txt
  artifacts/<stage>.json
  report.md
```

Raw responses are preserved before deterministic JSON extraction and contract validation.

## Leasing

A worker claims a pending job inside `BEGIN IMMEDIATE`, records a worker id, and writes a lease. Heartbeats extend the lease. Only the worker that owns the active lease may finish the job. Expired leases are requeued until the retry budget is exhausted.

## Stage context

Each job receives:

- research question;
- requester;
- current stage;
- all prior validated artifacts.

The deterministic VALIDATE stage checks the acquired manifest rather than asking a model to self-certify its own data.

## Deployment

`deploy-all.sh` performs:

1. compile, unit/integration, and shell checks;
2. controller service installation on SZ81;
3. retirement of the old watchdog units;
4. Hermes plugin/helper installation on HK43;
5. plugin enablement and gateway restart attempt;
6. cross-host health checks.

The deploy is intentionally fail-fast except for restarting an unknown Hermes gateway service name. Set `HERMES_GATEWAY_SERVICE` when the user service has a non-default name.

## Operational commands

```bash
systemctl status multi-agent-pipeline-worker.timer
systemctl status multi-agent-pipeline-notify.timer
journalctl -u multi-agent-pipeline-worker.service -n 100 --no-pager
journalctl -u multi-agent-pipeline-notify.service -n 100 --no-pager

python3 implementation/scripts/reliable_ctl.py \
  --db implementation/state/pipeline.db \
  --runs-dir implementation/state/runs list
```

A blocked run may be explicitly reopened after the evidence or adapter issue is corrected:

```bash
python3 implementation/scripts/reliable_ctl.py \
  --db implementation/state/pipeline.db \
  --runs-dir implementation/state/runs retry RUN_ID
```
