# Official DeerFlow Financial Research Integration

This directory configures the official `bytedance/deer-flow` 2.x agent harness for the Codex-led financial research system.

It does **not** implement the user's custom financial-data service. That service must be connected through the MCP contract in `docs/FINANCE_DATA_MCP_CONTRACT.md`.

## Files

```text
integrations/deerflow/
├── agents/
│   ├── finance-evidence-agent.json
│   ├── industry-research-agent.json
│   └── quant-analysis-agent.json
├── config.finance-research.example.yaml
├── deployment-manifest.example.json
└── extensions_config.finance-research.example.json
```

## Deployment sequence

### 1. Pin official DeerFlow

Clone or deploy a reviewed official tag/commit. Record it in a copy of:

```text
deployment-manifest.example.json
```

Do not use `main`, `master`, `HEAD`, or `latest` as the production identity.

### 2. Merge the configuration fragment

Merge `config.finance-research.example.yaml` into the official DeerFlow `config.yaml` and replace container image tags with a digest-pinned deployment.

The fragment intentionally disables research-memory injection and Skill Evolution, enables Tool Search and token limits, uses an isolated sandbox, and installs a global tool allowlist.

### 3. Implement the real financial-data MCP server

Replace the placeholder module in `extensions_config.finance-research.example.json` with the real server implementation.

The placeholder is designed to fail `scripts/deerflow_preflight.py`; it must never pass production preflight unchanged.

### 4. Synchronize Custom Agents

```bash
for spec in integrations/deerflow/agents/*.json; do
  python adapters/deerflow_gateway.py sync-agent --spec "$spec"
done
```

Record the synchronization timestamp in the deployment manifest.

### 5. Hash deployed configuration

Compute SHA-256 for the actual official DeerFlow `config.yaml` and `extensions_config.json`, then record the values in the deployment manifest.

```bash
sha256sum /path/to/deer-flow/config.yaml
sha256sum /path/to/deer-flow/extensions_config.json
```

### 6. Run deterministic preflight

```bash
python scripts/deerflow_preflight.py \
  --deployment-manifest /path/to/deployment-manifest.json \
  --config /path/to/deer-flow/config.yaml \
  --extensions-config /path/to/deer-flow/extensions_config.json \
  --report runs/<run_id>/deerflow_preflight_report.json
```

When the Custom Agent management API has been disabled after synchronization, add:

```bash
--skip-live-agent-inventory
```

That option skips only the live `/api/agents` inventory check. It does not skip health, manifest, configuration hash, MCP placeholder, or security-control checks.

For a build-time offline configuration check, add `--offline`. A production run should still perform a live health check before dispatching tasks.

## Expected failure of repository examples

The repository examples are templates, not deployment evidence. `deployment-manifest.example.json` contains an unpinned reference and null hashes; `extensions_config.finance-research.example.json` contains a placeholder MCP module. The preflight must fail against these files until they are copied and completed with real deployment values.

## Trust boundary

```text
Codex plan
  -> official DeerFlow Custom Agent
  -> financial-data MCP tool
  -> custom financial-data service
  -> immutable snapshot + manifest metadata
  -> deterministic acquisition gate
```

A DeerFlow response, event trace, Custom Agent statement, MCP success flag, or deployment manifest is not enough to validate a financial value. Validation still depends on preserved source snapshots and the deterministic gates in `scripts/validate_evidence.py`.
