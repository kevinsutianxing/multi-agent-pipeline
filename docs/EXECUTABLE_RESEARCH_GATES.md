# Executable Financial Research Gates

## Purpose

The repository already defines a financial research constitution, data trust contract, agent coordination model, and a Codex planner prompt. This document closes the main implementation gap: a model's statement that data was checked is not itself validation evidence.

The executable layer therefore uses two independent control mechanisms:

1. deterministic scripts validate files, dates, hashes, lineage, and claim coverage;
2. an independent reviewer challenges methodology and interpretation after deterministic checks pass.

## Main correction to the original pipeline

The original six-phase pipeline uses an `agent()` call to perform the data gate and return `overall_pass`. JSON schema validation guarantees that the answer has the expected shape; it does not prove that the underlying data is correct.

For financial research, replace model-declared gates with this sequence:

```text
DeerFlow data worker --------> source_manifest.data.json ----+
                                                              |
DeerFlow research worker ----> source_manifest.research.json -+--> merge_manifests.py
                                                              |
DeerFlow data worker --------> dataset_manifest.json ---------+
                                                                    |
                                                                    v
                                                       validate_evidence.py
                                                       --stage acquisition
                                                                    |
                                                                    v
                                                            analysis allowed
                                                                    |
                                                                    v
                                         calculation_manifest + claim_ledger
                                                                    |
                                                                    v
                                                       validate_evidence.py
                                                       --stage release
                                                                    |
                                                                    v
                                                 independent adversarial review
                                                                    |
                                                                    v
                                                              release decision
```

## Why there are two data gates

### Acquisition gate

Runs before analysis:

```bash
python scripts/merge_manifests.py --run-dir runs/<run_id>
python scripts/validate_evidence.py \
  --run-dir runs/<run_id> \
  --as-of YYYY-MM-DD \
  --stage acquisition
```

It validates sources and datasets without requiring calculations or claims that do not exist yet.

### Release gate

Runs after analysis and reproduction:

```bash
python scripts/validate_evidence.py \
  --run-dir runs/<run_id> \
  --as-of YYYY-MM-DD \
  --stage release
```

It additionally validates calculation lineage, claim references, contradictions, and 100% support coverage for material claims.

## Evidence graph

The final report is a view over this graph:

```text
source -> immutable snapshot -> dataset -> calculation -> claim -> paragraph/chart
```

Every edge must be represented by stable IDs. Raw snapshots and material calculation outputs must carry SHA-256 hashes.

## Source record minimum

Each source/evidence record must include:

- `evidence_id` and `source_id`;
- provider and source locator;
- redacted request parameters where applicable;
- `retrieved_at`, `as_of`, `published_at`, and `available_at` where relevant;
- immutable snapshot path and SHA-256;
- source tier and verification status.

`available_at` is essential for point-in-time research. An observation can describe an old period yet still be future information if it was not published or available by the historical as-of date.

## Dataset record minimum

Each dataset record must include:

- stable dataset ID and source IDs;
- raw snapshot path and SHA-256;
- observation window and maximum availability date;
- timezone, frequency, unit, currency where relevant, and adjustment convention;
- row count, schema fingerprint, missingness, duplicate rate, and thresholds;
- validation status;
- explicit proxy/synthetic flag and approval when applicable.

## Claim ledger rule

Every material statement must be classified as one of:

- `FACT`;
- `CALCULATION`;
- `INFERENCE`;
- `HYPOTHESIS`;
- `SCENARIO`.

A material fact requires evidence IDs. A material calculation requires calculation IDs. Material interpretations and scenarios require evidence and/or calculations. Unresolved material contradictions block release.

## Agent independence

Codex is the Chief Research Planner and Integrator, but may not self-certify data or final release readiness. Claude Code or another genuinely separate reviewer performs adversarial review.

Do not use the phrase "simulate independent review". A second pass by the same execution context is not independent review. If an independent reviewer is unavailable, return `NEEDS_HUMAN` or a blocked state.

## DeerFlow integration contract

Keep two logical adapters even when they share the same infrastructure:

- `deerflow-data`: financial data retrieval, raw snapshots, dataset manifest;
- `deerflow-research`: industry evidence collection and source manifest.

They write separate source-manifest segments to avoid concurrent writes. The deterministic merger creates the combined manifest.

The exact transport may be HTTP, MCP, CLI, or SDK. The invariant is:

```text
bounded request -> raw snapshot -> metadata manifest -> deterministic validation
```

A successful API response without an immutable snapshot and manifest is not research-grade evidence.

## Quantitative research additions

The deterministic evidence gate is necessary but not sufficient for a backtest. Quant research must separately test:

- point-in-time universe membership;
- corporate actions and adjustment convention;
- survivorship, revision, label, and feature leakage;
- train/validation/test or walk-forward protocol;
- benchmark and risk model selection;
- transaction costs, turnover, liquidity, slippage, and capacity;
- multiple testing and model-selection bias;
- sensitivity, ablation, and subperiod stability;
- statistical and economic significance;
- reproducible seeds and environment.

## Industry research additions

Industry/company research must separately test:

- value-chain taxonomy and entity mapping;
- primary-source hierarchy;
- observation date versus publication date;
- KPI definitions, unit, currency, and accounting comparability;
- demand, supply, price, inventory, capacity, utilization, margins, and market share where relevant;
- historical base rates;
- alternative causal explanations;
- bull/base/bear assumptions and disconfirming indicators;
- visibility of conflicting sources.

## Test command

```bash
python -m pytest -q tests/test_research_gates.py
```

The initial tests cover a valid release bundle, future-information blocking, unsupported material facts, acquisition-stage behavior before claims exist, and stable merging of parallel source manifests.
