# Deployment Model

The initial deployment is a control plane, not another autonomous agent daemon.

- **hermeskevin on HK43** creates and queries research runs.
- **SZ81** holds the canonical repository, run artifacts, deterministic controller, fmdata and DeerFlow adjacency.
- **Codex** plans and integrates; **Claude Code** independently reviews; **Hermes** retains context and routes work.
- The watchdog retries stale state evaluation, writes a recovery handoff, then escalates visibly after its bounded retry budget. It never marks an incomplete run successful.

Each run is stored in `runs/<run_id>/`. The required artifacts are `task.json`, `state.json`, `handoff.json`, and one gate artifact per stage. Reports and evidence bundles stay inside the same run directory.

## Operations

```bash
python3 scripts/researchctl.py create --question '研究某公司' --requester manual
python3 scripts/researchctl.py status RUN_ID
python3 scripts/researchctl.py watch --all
python3 scripts/stage_dispatch.py RUN_ID          # deterministic integration test
python3 scripts/stage_dispatch.py --execute RUN_ID # only for Codex/Claude stages with live model calls
python3 -m unittest discover -s tests -v
```

The systemd timer runs the watchdog every five minutes. A blocked state is a required outcome when evidence, validation, review, or a human decision is missing. Final blocking events create one `alert.json`; the watchdog routes it through hermeskevin to the most recently active Feishu conversation, then marks it delivered to prevent duplicate notifications.

`stage_dispatch.py` records a per-stage receipt with input fingerprint and raw response. It will not repeat a successful identical stage. The default mode is deterministic mock execution for integration testing; `--execute` only enables the safe Codex and Claude adapters. Source collection and long-form analysis remain deliberately blocked until their source-specific Hermes/DeerFlow adapters are approved.
