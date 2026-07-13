# Reference Examples

Files in this directory are non-production examples. They may demonstrate earlier Claude Code Workflow/`cc-connect` patterns, task shapes, prompts, or orchestration ideas, but they are not part of the supported deployed runtime.

## Rules

- Do not invoke these examples from systemd, the Hermes ingress plugin, or production deployment scripts.
- Do not create a queue, controller, watchdog, dispatcher, state store, or notification path here.
- Do not copy an example into production without adapting it to the contracts and tests under `implementation/`.
- Mark synthetic or illustrative data explicitly.
- Never represent an example result as validated financial research.

The only supported runtime is under [`../implementation/`](../implementation/README.md). See [`../docs/PROJECT_MAP.md`](../docs/PROJECT_MAP.md) for repository ownership boundaries.
