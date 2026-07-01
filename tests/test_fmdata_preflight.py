from __future__ import annotations

from scripts import fmdata_preflight


class FakeClient:
    base_url = "http://fmdata.test"

    def __init__(self, *, key="key", ready=True, contract="research-snapshot-v1"):
        self.research_key = key
        self.ready = ready
        self.contract = contract

    def health(self):
        return {
            "status": "ok",
            "service": "fmdata",
            "contract": self.contract,
            "self_validation": False,
        }

    def catalog(self):
        return {
            "datasets": {
                "daily_basic": {
                    "rows": 10,
                    "research_ready": self.ready,
                    "limitations": [] if self.ready else ["missing adjustment"],
                    "semantics": {
                        "frequency": "daily",
                        "currency": "CNY",
                    },
                }
            }
        }


def test_preflight_passes_for_ready_required_dataset():
    report = fmdata_preflight.evaluate(
        FakeClient(),
        [
            {
                "dataset": "daily_basic",
                "research_ready": True,
                "expected_semantics": {"frequency": "daily", "currency": "CNY"},
            }
        ],
    )
    assert report["status"] == "PASS"
    assert report["summary"]["critical_count"] == 0


def test_preflight_fails_without_research_key():
    report = fmdata_preflight.evaluate(FakeClient(key=""), [])
    assert report["status"] == "FAIL"
    assert any(item["code"] == "MISSING_RESEARCH_KEY" for item in report["findings"])


def test_preflight_fails_for_unready_dataset():
    report = fmdata_preflight.evaluate(
        FakeClient(ready=False),
        [{"dataset": "daily_basic", "research_ready": True}],
    )
    assert report["status"] == "FAIL"
    assert any(
        item["code"] == "DATASET_NOT_RESEARCH_READY" for item in report["findings"]
    )


def test_preflight_fails_for_contract_mismatch():
    report = fmdata_preflight.evaluate(FakeClient(contract="legacy"), [])
    assert report["status"] == "FAIL"
    assert any(item["code"] == "CONTRACT_MISMATCH" for item in report["findings"])
