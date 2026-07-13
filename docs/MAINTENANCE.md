# Repository Maintenance Policy

This policy defines how the repository stays understandable, deployable, and auditable as multiple agents and maintainers change it.

## 1. Change classes

Every pull request must identify one primary change class:

- **Runtime:** state machine, worker, adapter, plugin, persistence, notification, or deployment behavior.
- **Research governance:** data trust, methodology, schemas, scoring, evidence, or review standards.
- **Operations:** service configuration, health checks, host integration, or runbooks.
- **Documentation:** explanatory changes that do not alter behavior.
- **Reference:** examples or compatibility material that is not deployed.

A pull request that mixes unrelated classes should be split unless the changes are inseparable and the coupling is explained.

## 2. Source of truth

- Runtime behavior: code and tests under `implementation/`.
- Runtime operation: `implementation/docs/AGENT_USAGE_GUIDE.md` and `implementation/docs/IMPLEMENTATION.md`.
- Repository structure: `docs/PROJECT_MAP.md`.
- Agent authority and escalation: `AGENTS.md`.
- Data acceptance: `docs/DATA_TRUST_CONTRACT.md`.
- Machine contracts: `schemas/`.

When two documents disagree, fix the disagreement rather than adding a third interpretation.

## 3. Compatibility and migrations

Runtime changes must state whether they affect:

- the SQLite schema;
- existing runs;
- persisted raw outputs or normalized artifacts;
- environment variables;
- systemd units;
- HK43/SZ81 SSH assumptions;
- Feishu ingress or notification routing.

Destructive migrations require explicit approval. Prefer additive migrations and deterministic recovery. Never require operators to edit SQLite rows manually.

## 4. Deprecation

A component may be deprecated only when:

1. its replacement is documented and tested;
2. production callers have migrated;
3. CI no longer depends on it;
4. the removal plan names affected files and services;
5. duplicate alerts or execution paths cannot remain active.

Deprecated production code should not remain indefinitely as an undocumented fallback. Reference material must be clearly marked non-production.

## 5. Validation levels

### Documentation-only

- links and paths checked;
- no runtime command is duplicated incorrectly;
- project map remains accurate.

### Runtime or operations

```bash
make test
```

Also run environment-specific checks when relevant:

```bash
make health
```

A successful unit test does not prove live HK43/SZ81 deployment, authentication, provider access, or Feishu delivery.

### Research-governance changes

In addition to repository tests, document:

- methodology impact;
- data-source impact;
- backward compatibility;
- independent review result;
- whether historical reports or scores would change.

## 6. Pull-request evidence

Every material PR must report:

- root cause or motivation;
- exact scope and files changed;
- behavior before and after;
- migration and deployment impact;
- tests and checks run;
- data sources touched, if any;
- remaining environment-dependent risks;
- reviewer result.

## 7. Repository hygiene

Do not commit:

- SQLite databases;
- run state or generated reports;
- `.env` files or credentials;
- model caches and Python caches;
- copied vendor responses containing secrets;
- temporary deployment archives;
- local host aliases or private keys.

Prefer small authoritative documents, links, and generated validation over copied instructions. Remove dead references in the same PR that removes their target.

## 8. Release discipline

A change may be merged when:

- required CI passes;
- the PR is mergeable and reviewed at the appropriate level;
- runtime docs match actual commands;
- migration impact is explicit;
- no second execution path is introduced;
- live deployment status is stated honestly as verified or unverified.

Deployment is a separate act from merging. Record the deployed commit SHA and health-check result when production deployment is performed.
