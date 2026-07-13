#!/usr/bin/env python3
"""Deterministic control plane for evidence-gated research runs."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


STAGES = (
    "QUALIFY",
    "PLAN",
    "ACQUIRE_DATA",
    "VALIDATE_DATA",
    "ANALYZE",
    "REVIEW",
    "DELIVER",
    "RECORD",
)
TERMINAL_STATUSES = {
    "DONE",
    "BLOCKED_DATA_UNAVAILABLE",
    "BLOCKED_DATA_INVALID",
    "BLOCKED_METHODOLOGY_REVIEW_REQUIRED",
    "BLOCKED_HUMAN_DECISION_REQUIRED",
    "FAILED_GATES",
    "BUDGET_EXHAUSTED",
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def has_fields(value: dict[str, Any] | None, fields: tuple[str, ...]) -> bool:
    return bool(value) and all(field in value for field in fields)


class ResearchController:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.runs_dir = root / "runs"
        self.config = read_json(root / "config" / "controller.json") or {}

    @property
    def timeout_seconds(self) -> int:
        return int(self.config.get("stage_timeout_seconds", 1800))

    @property
    def max_recovery_attempts(self) -> int:
        return int(self.config.get("max_recovery_attempts", 2))

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def load_state(self, run_id: str) -> dict[str, Any]:
        state = read_json(self.run_dir(run_id) / "state.json")
        if not state:
            raise ValueError(f"Unknown run: {run_id}")
        return state

    def save_state(self, run_id: str, state: dict[str, Any]) -> None:
        state["updated_at"] = utc_now()
        write_json(self.run_dir(run_id) / "state.json", state)

    def event(self, state: dict[str, Any], kind: str, detail: str) -> None:
        state.setdefault("events", []).append({"at": utc_now(), "kind": kind, "detail": detail})

    def create(self, question: str, research_type: str, requester: str, as_of_date: str | None) -> str:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("Research question must not be empty")
        run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        run_dir = self.run_dir(run_id)
        run_dir.mkdir(parents=True)
        write_json(
            run_dir / "task.json",
            {
                "task_id": run_id,
                "research_question": normalized_question,
                "research_type": research_type,
                "requester": requester,
                "as_of_date": as_of_date or datetime.now(UTC).date().isoformat(),
                "allowed_sources": ["user_material", "filing", "fmdata", "mx", "info_bridge", "gangtise", "zsxq"],
                "forbidden_sources": ["uncited_social_media_as_fact"],
                "required_outputs": ["research_report", "evidence_bundle"],
                "validation_gates": ["source_identity", "freshness", "completeness", "unit_currency", "conclusion_strength"],
                "stop_conditions": ["missing_primary_evidence", "failed_data_validation", "unresolved_critical_review"],
            },
        )
        state = {
            "run_id": run_id,
            "status": "INTAKE",
            "current_stage": "QUALIFY",
            "stage_started_at": utc_now(),
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "recovery_attempts": {},
            "events": [],
        }
        self.event(state, "CREATED", f"Created by {requester}")
        self.save_state(run_id, state)
        self.write_handoff(run_id, state, "Awaiting qualification by the research planner.")
        return run_id

    def write_handoff(self, run_id: str, state: dict[str, Any], instruction: str) -> None:
        task = read_json(self.run_dir(run_id) / "task.json") or {}
        handoff = {
            "run_id": run_id,
            "status": state["status"],
            "current_stage": state["current_stage"],
            "research_question": task.get("research_question"),
            "instruction": instruction,
            "required_artifact": self.required_artifact(state["current_stage"]),
            "updated_at": utc_now(),
        }
        write_json(self.run_dir(run_id) / "handoff.json", handoff)

    def raise_alert(self, run_id: str, state: dict[str, Any], reason: str) -> None:
        alert_path = self.run_dir(run_id) / "alert.json"
        existing = read_json(alert_path)
        if existing and existing.get("delivered_at"):
            return
        write_json(
            alert_path,
            {
                "run_id": run_id,
                "status": state["status"],
                "stage": state["current_stage"],
                "reason": reason,
                "created_at": existing.get("created_at", utc_now()) if existing else utc_now(),
                "delivered_at": None,
            },
        )

    def mark_alert_delivered(self, run_id: str) -> None:
        alert_path = self.run_dir(run_id) / "alert.json"
        alert = read_json(alert_path)
        if not alert:
            raise ValueError(f"No alert exists for run: {run_id}")
        alert["delivered_at"] = utc_now()
        write_json(alert_path, alert)

    def required_artifact(self, stage: str) -> str:
        return {
            "QUALIFY": "qualification.json",
            "PLAN": "plan.json",
            "ACQUIRE_DATA": "data_manifest.json",
            "VALIDATE_DATA": "data_validation.json",
            "ANALYZE": "analysis.json",
            "REVIEW": "review.json",
            "DELIVER": "delivery.json",
            "RECORD": "record.json",
        }[stage]

    def evaluate_stage(self, run_id: str, stage: str) -> tuple[bool, str, str | None]:
        run_dir = self.run_dir(run_id)
        if stage == "QUALIFY":
            artifact = read_json(run_dir / "qualification.json")
            if not has_fields(artifact, ("qualified", "data_routes", "methodology_risk")):
                return False, "qualification.json missing required fields", None
            if not artifact["qualified"]:
                return False, "qualification requires a human methodology decision", "BLOCKED_HUMAN_DECISION_REQUIRED"
        elif stage == "PLAN":
            artifact = read_json(run_dir / "plan.json")
            if not has_fields(artifact, ("research_question", "hypotheses", "data_requests", "validation_plan", "review_plan")):
                return False, "plan.json missing required fields", None
        elif stage == "ACQUIRE_DATA":
            artifact = read_json(run_dir / "data_manifest.json")
            if not has_fields(artifact, ("datasets", "retrieved_at")) or not isinstance(artifact["datasets"], list):
                return False, "data_manifest.json missing dataset metadata", None
            if not artifact["datasets"]:
                return False, "no datasets acquired", "BLOCKED_DATA_UNAVAILABLE"
            required_dataset_fields = ("dataset_id", "source_system", "source_name", "retrieved_at", "validation_status")
            if any(not has_fields(dataset, required_dataset_fields) for dataset in artifact["datasets"]):
                return False, "dataset metadata is incomplete", "BLOCKED_DATA_INVALID"
        elif stage == "VALIDATE_DATA":
            artifact = read_json(run_dir / "data_validation.json")
            if not has_fields(artifact, ("overall_pass", "checks", "validated_at")):
                return False, "data_validation.json missing required fields", None
            if not artifact["overall_pass"]:
                return False, "data validation failed", "BLOCKED_DATA_INVALID"
        elif stage == "ANALYZE":
            artifact = read_json(run_dir / "analysis.json")
            if not has_fields(artifact, ("claims", "methodology", "limitations")):
                return False, "analysis.json missing claims, methodology, or limitations", None
        elif stage == "REVIEW":
            artifact = read_json(run_dir / "review.json")
            if not has_fields(artifact, ("passed", "findings", "reviewer")):
                return False, "review.json missing required fields", None
            if not artifact["passed"]:
                return False, "independent review has unresolved critical findings", "FAILED_GATES"
        elif stage == "DELIVER":
            artifact = read_json(run_dir / "delivery.json")
            if not has_fields(artifact, ("report_path", "evidence_bundle", "delivered")):
                return False, "delivery.json missing required fields", None
            report = (run_dir / artifact["report_path"]).resolve()
            try:
                report.relative_to(run_dir.resolve())
            except ValueError:
                return False, "delivery report_path must stay inside the run directory", "FAILED_GATES"
            if not report.is_file():
                return False, "delivery report_path does not exist inside the run", None
            if not artifact["delivered"]:
                return False, "delivery is not confirmed", None
        elif stage == "RECORD":
            artifact = read_json(run_dir / "record.json")
            if not has_fields(artifact, ("recorded", "summary_path")) or not artifact["recorded"]:
                return False, "record.json missing confirmed archival", None
        return True, "stage passed", None

    def advance(self, run_id: str) -> dict[str, Any]:
        state = self.load_state(run_id)
        if state["status"] in TERMINAL_STATUSES:
            return state
        stage = state["current_stage"]
        passed, detail, blocked_status = self.evaluate_stage(run_id, stage)
        if blocked_status:
            state["status"] = blocked_status
            self.event(state, "BLOCKED", detail)
            self.write_handoff(run_id, state, detail)
            self.raise_alert(run_id, state, detail)
            self.save_state(run_id, state)
            return state
        if not passed:
            self.write_handoff(run_id, state, detail)
            self.save_state(run_id, state)
            return state
        next_index = STAGES.index(stage) + 1
        if next_index == len(STAGES):
            state["status"] = "DONE"
            self.event(state, "COMPLETED", "All deterministic gates passed")
            self.write_handoff(run_id, state, "Run completed. Preserve this evidence bundle for reuse.")
        else:
            state["status"] = "ACTIVE"
            state["current_stage"] = STAGES[next_index]
            state["stage_started_at"] = utc_now()
            self.event(state, "ADVANCED", f"{stage} -> {state['current_stage']}")
            self.write_handoff(run_id, state, f"Provide {self.required_artifact(state['current_stage'])} to continue.")
        self.save_state(run_id, state)
        return state

    def watch_run(self, run_id: str, stale_after_seconds: int | None = None) -> dict[str, Any]:
        state = self.advance(run_id)
        if state["status"] in TERMINAL_STATUSES:
            return state
        stage_started = datetime.fromisoformat(state["stage_started_at"].replace("Z", "+00:00"))
        age = (datetime.now(UTC) - stage_started).total_seconds()
        timeout = stale_after_seconds if stale_after_seconds is not None else self.timeout_seconds
        if age < timeout:
            return state
        stage = state["current_stage"]
        attempts = int(state.setdefault("recovery_attempts", {}).get(stage, 0)) + 1
        state["recovery_attempts"][stage] = attempts
        if attempts <= self.max_recovery_attempts:
            self.event(state, "RECOVERY_RETRY", f"{stage} stale for {int(age)}s; retry {attempts}/{self.max_recovery_attempts}")
            self.write_handoff(run_id, state, f"Recovery retry {attempts}: {stage} is stale. Re-check the required artifact and service health before continuing.")
        else:
            state["status"] = "BLOCKED_HUMAN_DECISION_REQUIRED"
            self.event(state, "ESCALATED", f"{stage} exceeded {self.max_recovery_attempts} recovery attempts")
            self.write_handoff(run_id, state, f"Escalated: {stage} remains stale after automated retries. Do not claim completion; inspect events and recovery attempts.")
            self.raise_alert(run_id, state, f"{stage} exceeded the bounded recovery budget")
        self.save_state(run_id, state)
        return state

    def watch_all(self, stale_after_seconds: int | None = None) -> list[dict[str, Any]]:
        if not self.runs_dir.exists():
            return []
        results = []
        for state_path in sorted(self.runs_dir.glob("*/state.json")):
            results.append(self.watch_run(state_path.parent.name, stale_after_seconds))
        return results

    def status(self, run_id: str) -> dict[str, Any]:
        return self.load_state(run_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--question")
    create.add_argument("--question-stdin", action="store_true")
    create.add_argument("--research-type", default="deep_research")
    create.add_argument("--requester", default="manual")
    create.add_argument("--as-of-date")
    for command in ("advance", "status"):
        subparsers.add_parser(command).add_argument("run_id")
    subparsers.add_parser("mark-alert-delivered").add_argument("run_id")
    watch = subparsers.add_parser("watch")
    watch.add_argument("--run-id")
    watch.add_argument("--all", action="store_true")
    watch.add_argument("--stale-after-seconds", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    controller = ResearchController(args.root)
    if args.command == "create":
        question = sys.stdin.read() if args.question_stdin else (args.question or "")
        result: Any = {"run_id": controller.create(question, args.research_type, args.requester, args.as_of_date)}
    elif args.command == "advance":
        result = controller.advance(args.run_id)
    elif args.command == "status":
        result = controller.status(args.run_id)
    elif args.command == "mark-alert-delivered":
        controller.mark_alert_delivered(args.run_id)
        result = {"run_id": args.run_id, "alert_delivered": True}
    else:
        if args.all == bool(args.run_id):
            raise SystemExit("watch requires exactly one of --run-id or --all")
        result = controller.watch_all(args.stale_after_seconds) if args.all else controller.watch_run(args.run_id, args.stale_after_seconds)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
