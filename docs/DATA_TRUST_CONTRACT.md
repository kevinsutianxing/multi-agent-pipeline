# Data Trust Contract

This contract defines the minimum standard for financial data before any agent may use it in quantitative research, industry research, market monitoring, valuation work, or generated reports.

## Core rule

A financial dataset is not research-grade until it is both **retrieved** and **validated**.

Retrieval alone is insufficient. A successful API response is not proof that the data is correct, complete, timely, point-in-time safe, or fit for the intended research question.

## Data trust levels

| Level | Name | Allowed use |
|---|---|---|
| L0 | Unseen | Do not use. |
| L1 | Retrieved | May inspect only. Do not cite or model. |
| L2 | Parsed | May run validation checks. Do not conclude. |
| L3 | Validated | May use for descriptive analysis. |
| L4 | Research-grade | May use for models, backtests, and published reports. |
| L5 | Audited | May use for high-stakes recurring research after independent review. |

## Required metadata

Every dataset artifact must carry this metadata sidecar:

```yaml
dataset_id: string
source_system: deerflow | vendor | exchange | filing | official_statistics | web | manual
source_name: string
source_endpoint: string
retrieval_method: api | file | scrape | manual | derived
retrieved_at: ISO-8601 datetime
as_of_date: YYYY-MM-DD
observation_start: YYYY-MM-DD
observation_end: YYYY-MM-DD
entity_type: equity | index | fund | macro | financial_statement | industry | news | alternative | other
entity_ids: list
field_names: list
frequency: tick | intraday | daily | weekly | monthly | quarterly | annual | irregular
unit_map: object
currency_map: object
timezone: string
adjustment_policy: raw | split_adjusted | dividend_adjusted | total_return | point_in_time | restated | unknown
license_or_usage_note: string
validation_status: pending | passed | failed | waived
validation_evidence: string
known_limitations: list
```

## Validation gates

### 1. Source identity gate

Confirm that the source is the intended source.

Checks:

- endpoint or dataset name matches configuration
- symbol/entity mapping is explicit
- exchange, currency, and market are correct
- duplicate aliases are resolved
- deprecated symbols are rejected or mapped with evidence

### 2. Freshness gate

Checks:

- `retrieved_at` exists
- `as_of_date` is not after current run date unless explicitly synthetic
- latest observation date is plausible for source frequency
- stale data is flagged rather than silently used

### 3. Completeness gate

Checks:

- required fields exist
- required dates exist
- missingness is quantified
- sparse series are not silently forward-filled
- coverage meets task-specific threshold

### 4. Unit and currency gate

Checks:

- units are explicit
- currency is explicit
- price, return, percentage, bps, and ratio fields are not mixed
- FX conversions record rate source and date

### 5. Time alignment gate

Checks:

- observation date and availability date are separated when needed
- market calendars are respected
- event windows do not include future observations
- period-end and filing-date data are not confused

### 6. Range and sanity gate

Checks:

- prices and shares are non-negative when required
- returns are within plausible bounds unless explained
- financial statement fields satisfy basic accounting relationships where applicable
- macro fields are checked against expected sign and scale

### 7. Cross-source reconciliation gate

For high-impact claims, compare with at least one independent reference source where possible.

Examples:

- price data versus exchange/vendor reference
- financial statement values versus filing/vendor
- macro data versus official statistics
- industry shipments versus company disclosures or official bodies

### 8. Transformation audit gate

Any derived dataset must log:

- input dataset IDs
- formulas
- filters
- joins
- resampling rules
- winsorization or outlier rules
- imputation rules
- version of code used

### 9. Point-in-time safety gate

Required for backtests, factor research, signal research, event studies, and historical reports.

Checks:

- no observations later than `as_of_date`
- no restated values unless explicitly modeled as restated research
- no future index constituents
- no survivorship-only universe unless disclosed
- no model training on future labels

### 10. Research fitness gate

The dataset must be valid for the specific research task, not merely valid in isolation.

Examples:

- Intraday trading research cannot rely on daily close-only data.
- As-of valuation work cannot use later revised estimates.
- Industry trend research cannot treat rumor/news estimates as audited financial data.

## Waiver policy

A validation failure may be waived only if:

1. the waiver is explicit;
2. the research output clearly labels the limitation;
3. the data is not used for unsupported precision;
4. the waiver is reviewed by the research owner or independent reviewer.

Waived data cannot exceed trust level L3 unless the waiver is itself audited.

## Prohibited behavior

Agents must not:

- fabricate missing values;
- fill gaps without recording the rule;
- silently change units;
- infer symbols without confirmation;
- treat estimates as facts;
- treat model outputs as source data;
- cite unvalidated data in final conclusions;
- hide validation failures in appendices only;
- continue a backtest after leakage is detected.

## Dataset acceptance record

Each accepted dataset should produce a record like:

```json
{
  "dataset_id": "example",
  "trust_level": "L4",
  "validation_status": "passed",
  "failed_checks": [],
  "waivers": [],
  "evidence_path": "runs/2026-07-01/example/data_validation.json",
  "approved_for": ["descriptive_analysis", "backtest"],
  "not_approved_for": ["investment_recommendation"]
}
```
