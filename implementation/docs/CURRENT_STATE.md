# Current State

## Resolved

- One SQLite-backed state machine replaces the disconnected v1/v2 paths.
- Repository paths consistently include `implementation/`.
- A supervised worker timer consumes pending jobs.
- A supervised notifier timer flushes durable messages.
- Worker jobs include the research question and all prior validated artifacts.
- Model output is stored raw, then normalized from plain JSON, fenced JSON, wrapped results, or prefaced output.
- SQLite claims are atomic and lease-aware; stale workers cannot submit results.
- Notifications retain the exact Feishu conversation target recorded at ingress.
- The Hermes ingress hook uses stdin for the research question and returns `skip`, preventing shell injection and duplicate native dispatch.
- The old watchdog/controller files and units are removed.
- GitHub Actions runs compile, unit/integration, and shell syntax checks.

## Local validation

The refactor was validated with 17 isolated tests covering:

- duplicate ingress idempotency;
- question and prior-artifact propagation;
- full six-stage completion and report persistence;
- JSON normalization variants;
- retry and hard-block behavior;
- atomic lease ownership and stale-worker rejection;
- legacy SQLite migration;
- deterministic acquired-data validation;
- durable exact-target notifications;
- Feishu ingress interception and safe stdin transport.

## Environment-dependent checks

The following can only be confirmed on HK43/SZ81 during deployment:

- SSH aliases and host reachability;
- Codex and Claude authentication;
- `hermescold` profile and skill availability;
- Hermes gateway service name;
- provider availability and rate limits;
- fmdata/DeerFlow data-source health.

Run `implementation/deploy/deploy-all.sh` and then `implementation/deploy/healthcheck.sh` on SZ81. A provider-side 503 remains an external failure; the pipeline now records it, retries within budget, and blocks visibly rather than silently advancing.
