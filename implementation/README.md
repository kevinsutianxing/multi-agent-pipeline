# Reliable Multi-Agent Research Runtime

This directory contains the repository's only supported deployable runtime. The earlier file-state controller and watchdog were removed because they created a second, disconnected execution path.

Agents operating or modifying this runtime must first read [`docs/AGENT_USAGE_GUIDE.md`](docs/AGENT_USAGE_GUIDE.md). It defines supported commands, stage contracts, recovery rules, prohibited legacy paths, and the definition of done.

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

## Deploy

From the repository root on SZ81:

```bash
implementation/deploy/deploy-all.sh
```

Configuration is installed at `/etc/multi-agent-pipeline.env`. Review `config/pipeline.env.example` before production use, especially the SSH aliases and agent commands.

## Verify

```bash
implementation/deploy/healthcheck.sh
python3 implementation/scripts/reliable_ctl.py \
  --db implementation/state/pipeline.db \
  --runs-dir implementation/state/runs health
```

Create a smoke task:

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

```bash
python3 -m compileall -q implementation/scripts implementation/plugins implementation/tests
python3 -m unittest discover -s implementation/tests -v
bash -n implementation/deploy/*.sh
```
