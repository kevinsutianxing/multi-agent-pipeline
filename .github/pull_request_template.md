## Change class

- [ ] Runtime
- [ ] Research governance
- [ ] Operations
- [ ] Documentation
- [ ] Reference/example

## Root cause or motivation

Describe the problem being solved and why the change is necessary.

## Scope

### Changed

- 

### Explicitly unchanged

- 

## Behavior before and after

**Before:**

**After:**

## Data and methodology impact

- Data sources touched: none / list
- Methodology or scoring changed: no / explain
- Historical outputs affected: no / explain

## Migration and deployment impact

- SQLite schema or existing runs:
- Environment variables:
- systemd/services:
- HK43/SZ81/SSH assumptions:
- Feishu ingress or notifications:

## Validation

```bash
make test
```

Additional checks:

- [ ] Isolated tests passed
- [ ] GitHub Actions passed
- [ ] `make health` passed where applicable
- [ ] Live deployment verified, or explicitly marked unverified

## Evidence and review

- Files/logs/artifacts inspected:
- Independent reviewer result:
- Known limitations:
- Remaining environment-dependent risks:

## Safety checklist

- [ ] No second queue, controller, watchdog, dispatcher, or execution path was introduced
- [ ] Raw responses and evidence gates remain intact
- [ ] No direct SQLite mutation is required
- [ ] Documentation matches actual commands
- [ ] No secrets, local databases, generated run state, or reports are committed
