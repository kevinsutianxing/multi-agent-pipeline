from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import pytest

from scripts import research_control


def read_state(run_dir: Path) -> dict:
    return json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))


def test_init_serializes_as_of_date(tmp_path: Path) -> None:
    args = argparse.Namespace(
        run_dir=tmp_path,
        run_id="run-1",
        topic="test topic",
        research_type="mixed",
        as_of=dt.date(2026, 6, 30),
        force=False,
    )
    assert research_control.init_run(args) == 0
    state = read_state(tmp_path)
    brief = json.loads((tmp_path / "research_brief.json").read_text(encoding="utf-8"))
    assert state["state"] == "INTAKE"
    assert state["as_of"] == "2026-06-30"
    assert brief["as_of"] == "2026-06-30"


def test_checkpoint_requires_declared_artifacts(tmp_path: Path) -> None:
    research_control.write_json(
        tmp_path / "run_state.json",
        {"state": "INTAKE", "history": []},
    )
    research_control.write_json(tmp_path / "research_brief.json", {"run_id": "run-1"})
    args = argparse.Namespace(run_dir=tmp_path, phase="PLANNED")
    with pytest.raises(ValueError, match="research_plan.json"):
        research_control.checkpoint(args)


def test_sensitive_release_without_human_approval_stops(tmp_path: Path) -> None:
    research_control.write_json(
        tmp_path / "run_state.json",
        {"state": "REVIEWED", "history": []},
    )
    for filename in (
        "acquisition_gate_report.json",
        "release_data_gate_report.json",
        "reproducibility_report.json",
        "review_report.json",
    ):
        research_control.write_json(tmp_path / filename, {"status": "PASS"})
    research_control.write_json(
        tmp_path / "release_requirements.json",
        {
            "methodology_changed": True,
            "human_approved": False,
        },
    )
    (tmp_path / "candidate.md").write_text("candidate", encoding="utf-8")
    args = argparse.Namespace(run_dir=tmp_path, candidate="candidate.md")
    assert research_control.release(args) == 1
    assert read_state(tmp_path)["state"] == "NEEDS_HUMAN"
