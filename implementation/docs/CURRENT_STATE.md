# Current State and Known Gaps

## What exists

- `scripts/reliable_pipeline.py` implements a SQLite-backed v2 state machine.
- `scripts/reliable_worker.py` persists every worker attempt and raw response.
- `scripts/reliable_notify.py` delivers durable outbox entries and marks them sent only after command success.
- Unit and isolated end-to-end tests cover duplicate requests, invalid JSON, worker recovery, retry exhaustion, notification replay, stage events, and a fake six-stage run.

## What was observed in live use

- A live Codex qualification response met the minimal artifact contract and advanced one stage.
- Hermescold acquisition returned substantial raw research text but not the required JSON contract twice. V2 retained both raw responses and correctly blocked the run rather than advancing.
- `hermeskevin` can still bypass v2 and use its native leaf-subagent workflow. The current `agent:start` hook creates a v2 run but does not hard-intercept/skip the subsequent model dispatch.
- Existing v1 alert messages can appear alongside v2 messages and confuse users; v1 needs retirement once v2 owns the ingress path.
- V2 event/outbox persistence is implemented and tested. Production notification delivery was tested with a one-shot sender command, but a supervised sender service/timer is not yet installed.
- A provider-side GLM proxy queue saturation (`HTTP 503 queue full/timeout`) can block Hermes conversation replies independently of the pipeline.

## Required work before production enablement

1. Move research-trigger interception to the gateway pre-dispatch hook and return `skip` after creating a v2 run.
2. Add a supervised v2 worker scheduler and a supervised notification sender service.
3. Replace direct JSON-only agent contracts with raw-output capture plus a deterministic parser/normalizer, then validate the normalized artifact.
4. Retire v1 trigger/watchdog/alert routing after migration.
5. Add live integration tests for Feishu ingress, Codex, Hermescold, Claude review, and notification sender restart recovery.

## Safety position

V2 should not be advertised as a production autonomous research system until the ingress hard-intercept, scheduler, normalizer, and supervised sender are complete.
