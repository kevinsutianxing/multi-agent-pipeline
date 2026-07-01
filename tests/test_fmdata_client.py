from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from adapters import fmdata_client
from scripts import merge_dataset_manifests


class FakeFMDataClient:
    def __init__(self, manifest: dict, normalized: bytes, raw: bytes):
        self.manifest = manifest
        self.normalized = normalized
        self.raw = raw

    def create_snapshot(self, payload):
        return dict(self.manifest)

    def get_manifest(self, snapshot_id):
        assert snapshot_id == self.manifest["snapshot_id"]
        return dict(self.manifest)

    def download_snapshot(self, snapshot_id, *, raw=False):
        assert snapshot_id == self.manifest["snapshot_id"]
        return self.raw if raw else self.normalized


def sample_client(*, status: str = "OK", corrupt_hash: bool = False):
    normalized = b"trade_date,ts_code,close\n2026-06-30,000001.SZ,10.0\n"
    raw = b"provider-original\n"
    normalized_hash = hashlib.sha256(normalized).hexdigest()
    raw_hash = hashlib.sha256(raw).hexdigest()
    if corrupt_hash:
        normalized_hash = "0" * 64
    manifest = {
        "status": status,
        "snapshot_id": "fmdata-sample-abc",
        "source_id": "fmdata:tushare:sample:source",
        "evidence_id": "evidence:fmdata-sample-abc",
        "dataset_id": "fmdata:sample:dataset",
        "provider": "tushare",
        "source_locator": "fmdata://tushare/daily",
        "query_parameters": {"dataset": "sample", "as_of": "2026-06-30"},
        "request_sha256": "1" * 64,
        "retrieved_at": "2026-06-30T12:00:00+00:00",
        "as_of": "2026-06-30",
        "observation_start": "2026-06-30",
        "observation_end": "2026-06-30",
        "published_at": None,
        "available_at": "2026-06-30T10:00:00+00:00",
        "available_at_rule": None,
        "snapshot_path": "normalized/hash.csv",
        "content_sha256": normalized_hash,
        "raw_snapshot_path": "raw/hash.bin",
        "raw_content_sha256": raw_hash,
        "row_count": 1,
        "schema_fingerprint": "schema-v1",
        "timezone": "Asia/Shanghai",
        "frequency": "daily",
        "unit": "CNY/share",
        "currency": "CNY",
        "adjustment": "raw",
        "revision_policy": "original_provider_response",
        "recipe_sha256": "2" * 64,
        "limitations": [],
        "conflicts": [],
        "validation_status": "PENDING",
    }
    return FakeFMDataClient(manifest, normalized, raw)


def test_materialize_snapshot_verifies_and_writes_segments(tmp_path: Path):
    result = fmdata_client.materialize_snapshot(
        sample_client(),
        run_dir=tmp_path,
        task_id="market snapshot",
        request_payload={"dataset": "sample", "as_of": "2026-06-30"},
    )

    assert result["status"] == "MATERIALIZED"
    source_segment = json.loads(
        (tmp_path / result["source_manifest_segment"]).read_text(encoding="utf-8")
    )
    dataset_segment = json.loads(
        (tmp_path / result["dataset_manifest_segment"]).read_text(encoding="utf-8")
    )
    source = source_segment["sources"][0]
    dataset = dataset_segment["datasets"][0]
    assert source["verification_status"] == "VERIFIED"
    assert dataset["validation_status"] == "VALIDATED"
    assert dataset["missingness"] == 0
    assert dataset["duplicate_rate"] == 0
    assert (tmp_path / dataset["raw_path"]).is_file()


def test_non_ok_service_snapshot_is_not_promoted(tmp_path: Path):
    with pytest.raises(fmdata_client.FMDataError, match="not research-ready"):
        fmdata_client.materialize_snapshot(
            sample_client(status="PARTIAL"),
            run_dir=tmp_path,
            task_id="partial",
            request_payload={"dataset": "sample", "as_of": "2026-06-30"},
        )
    response = json.loads(
        (tmp_path / "fmdata" / "partial" / "response.json").read_text(encoding="utf-8")
    )
    assert response["status"] == "PARTIAL"
    assert not list(tmp_path.glob("dataset_manifest.*.json"))


def test_download_hash_mismatch_is_blocked(tmp_path: Path):
    with pytest.raises(fmdata_client.FMDataError, match="hash mismatch"):
        fmdata_client.materialize_snapshot(
            sample_client(corrupt_hash=True),
            run_dir=tmp_path,
            task_id="corrupt",
            request_payload={"dataset": "sample", "as_of": "2026-06-30"},
        )


def test_dataset_manifest_segments_merge_stably(tmp_path: Path):
    (tmp_path / "dataset_manifest.fmdata.b.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "ds-b", "row_count": 2}]}),
        encoding="utf-8",
    )
    (tmp_path / "dataset_manifest.fmdata.a.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "ds-a", "row_count": 1}]}),
        encoding="utf-8",
    )
    result = merge_dataset_manifests.merge(tmp_path)
    merged = json.loads((tmp_path / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert result["records"] == 2
    assert [item["dataset_id"] for item in merged["datasets"]] == ["ds-a", "ds-b"]


def test_conflicting_duplicate_dataset_ids_are_rejected(tmp_path: Path):
    (tmp_path / "dataset_manifest.one.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "same", "row_count": 1}]}),
        encoding="utf-8",
    )
    (tmp_path / "dataset_manifest.two.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "same", "row_count": 2}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="conflicting duplicate"):
        merge_dataset_manifests.merge(tmp_path)
