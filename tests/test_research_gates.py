from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import merge_manifests, validate_evidence


def write_valid_run(run_dir: Path) -> None:
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True)
    source_bytes = b"official filing snapshot\n"
    data_bytes = b"date,value\n2026-06-29,1.0\n"
    (raw_dir / "source.txt").write_bytes(source_bytes)
    (raw_dir / "dataset.csv").write_bytes(data_bytes)

    source_hash = hashlib.sha256(source_bytes).hexdigest()
    data_hash = hashlib.sha256(data_bytes).hexdigest()
    calc_hash = hashlib.sha256(b"1.0").hexdigest()

    (run_dir / "source_manifest.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "evidence_id": "ev-1",
                        "source_id": "src-1",
                        "provider": "official",
                        "locator": "official-filing-reference",
                        "retrieved_at": "2026-06-30T01:00:00Z",
                        "as_of": "2026-06-30",
                        "published_at": "2026-06-29T00:00:00Z",
                        "available_at": "2026-06-29T00:00:00Z",
                        "snapshot_path": "raw/source.txt",
                        "content_sha256": source_hash,
                        "verification_status": "VERIFIED",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    (run_dir / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "dataset_id": "ds-1",
                        "source_ids": ["src-1"],
                        "raw_path": "raw/dataset.csv",
                        "raw_sha256": data_hash,
                        "row_count": 1,
                        "observation_start": "2026-06-29",
                        "observation_end": "2026-06-29",
                        "max_available_at": "2026-06-29",
                        "timezone": "Asia/Shanghai",
                        "frequency": "daily",
                        "unit": "index",
                        "schema_fingerprint": "date:string,value:number",
                        "missingness": 0,
                        "duplicate_rate": 0,
                        "validation_status": "VALIDATED",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    (run_dir / "calculation_manifest.json").write_text(
        json.dumps(
            {
                "calculations": [
                    {
                        "calculation_id": "calc-1",
                        "input_dataset_ids": ["ds-1"],
                        "code_ref": "git:abc123/scripts/model.py",
                        "parameters": {"window": 20},
                        "output_hash": calc_hash,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    claims = [
        {
            "claim_id": "claim-1",
            "text": "The filing was published.",
            "classification": "FACT",
            "material": True,
            "evidence_ids": ["ev-1"],
            "status": "VERIFIED",
            "contradiction_status": "NONE",
            "as_of": "2026-06-30",
        },
        {
            "claim_id": "claim-2",
            "text": "The calculated value is 1.0.",
            "classification": "CALCULATION",
            "material": True,
            "calculation_ids": ["calc-1"],
            "status": "VERIFIED",
            "contradiction_status": "NONE",
            "as_of": "2026-06-30",
        },
    ]
    (run_dir / "claim_ledger.jsonl").write_text(
        "\n".join(json.dumps(row) for row in claims) + "\n",
        encoding="utf-8",
    )


def test_valid_release_run_passes(tmp_path: Path) -> None:
    write_valid_run(tmp_path)
    findings = []
    evidence = validate_evidence.validate_sources(
        tmp_path, validate_evidence.dt.date(2026, 6, 30), findings
    )
    datasets = validate_evidence.validate_datasets(
        tmp_path, validate_evidence.dt.date(2026, 6, 30), findings
    )
    calculations = validate_evidence.validate_calculations(
        tmp_path, datasets, findings
    )
    stats = validate_evidence.validate_claims(
        tmp_path,
        evidence,
        calculations,
        validate_evidence.dt.date(2026, 6, 30),
        findings,
    )
    assert not [finding for finding in findings if finding.severity == "CRITICAL"]
    assert stats["material_coverage"] == 1.0


def test_future_evidence_is_blocked(tmp_path: Path) -> None:
    write_valid_run(tmp_path)
    manifest = json.loads(
        (tmp_path / "source_manifest.json").read_text(encoding="utf-8")
    )
    manifest["sources"][0]["available_at"] = "2026-07-01T00:00:00Z"
    (tmp_path / "source_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    findings = []
    validate_evidence.validate_sources(
        tmp_path, validate_evidence.dt.date(2026, 6, 30), findings
    )
    assert any(
        finding.code == "FUTURE_AVAILABILITY"
        and finding.severity == "CRITICAL"
        for finding in findings
    )


def test_unsupported_material_fact_is_blocked(tmp_path: Path) -> None:
    write_valid_run(tmp_path)
    claim = {
        "claim_id": "claim-x",
        "text": "Unsupported fact",
        "classification": "FACT",
        "material": True,
        "status": "VERIFIED",
        "contradiction_status": "NONE",
    }
    (tmp_path / "claim_ledger.jsonl").write_text(
        json.dumps(claim) + "\n", encoding="utf-8"
    )
    findings = []
    validate_evidence.validate_claims(
        tmp_path,
        {"ev-1"},
        {"calc-1"},
        validate_evidence.dt.date(2026, 6, 30),
        findings,
    )
    assert any(
        finding.code == "UNSUPPORTED_MATERIAL_FACT" for finding in findings
    )


def test_acquisition_inputs_pass_before_claims_exist(tmp_path: Path) -> None:
    write_valid_run(tmp_path)
    (tmp_path / "claim_ledger.jsonl").unlink()
    (tmp_path / "calculation_manifest.json").unlink()
    findings = []
    validate_evidence.validate_sources(
        tmp_path, validate_evidence.dt.date(2026, 6, 30), findings
    )
    validate_evidence.validate_datasets(
        tmp_path, validate_evidence.dt.date(2026, 6, 30), findings
    )
    assert not [finding for finding in findings if finding.severity == "CRITICAL"]


def test_manifest_merge_is_stable(tmp_path: Path) -> None:
    (tmp_path / "source_manifest.research.json").write_text(
        json.dumps({"sources": [{"evidence_id": "ev-b"}]}),
        encoding="utf-8",
    )
    (tmp_path / "source_manifest.data.json").write_text(
        json.dumps({"sources": [{"evidence_id": "ev-a"}]}),
        encoding="utf-8",
    )
    result = merge_manifests.merge(tmp_path)
    merged = json.loads(
        (tmp_path / "source_manifest.json").read_text(encoding="utf-8")
    )
    assert result["records"] == 2
    assert [record["evidence_id"] for record in merged["sources"]] == [
        "ev-a",
        "ev-b",
    ]
