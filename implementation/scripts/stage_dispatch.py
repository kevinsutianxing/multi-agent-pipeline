#!/usr/bin/env python3
"""Idempotent stage dispatcher with mock and real Codex/Claude executors."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from researchctl import ResearchController, read_json, utc_now, write_json


ROLE_BY_STAGE = {
    "QUALIFY": "deterministic",
    "PLAN": "codex",
    "ACQUIRE_DATA": "hermescold",
    "VALIDATE_DATA": "deterministic",
    "ANALYZE": "hermescold",
    "REVIEW": "claude_code",
    "DELIVER": "codex",
    "RECORD": "deterministic",
}
REQUIRED_FIELDS = {
    "QUALIFY": ("qualified", "data_routes", "methodology_risk"),
    "PLAN": ("research_question", "hypotheses", "data_requests", "validation_plan", "review_plan"),
    "ACQUIRE_DATA": ("datasets", "retrieved_at"),
    "VALIDATE_DATA": ("overall_pass", "checks", "validated_at"),
    "ANALYZE": ("claims", "methodology", "limitations"),
    "REVIEW": ("passed", "findings", "reviewer"),
    "DELIVER": ("report_path", "evidence_bundle", "delivered"),
    "RECORD": ("recorded", "summary_path"),
}


def artifact_for(stage: str, task: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    if stage == "QUALIFY":
        return {"qualified": True, "data_routes": task["allowed_sources"], "methodology_risk": "review_required"}
    if stage == "PLAN":
        return {"research_question": task["research_question"], "hypotheses": [], "data_requests": [], "validation_plan": task["validation_gates"], "review_plan": ["claude_code"]}
    if stage == "ACQUIRE_DATA":
        return {"datasets": [{"dataset_id": "mock", "source_system": "test", "source_name": "mock", "retrieved_at": now, "validation_status": "passed"}], "retrieved_at": now}
    if stage == "VALIDATE_DATA":
        manifest = read_json(Path(task["_run_dir"]) / "data_manifest.json") or {}
        datasets = manifest.get("datasets", [])
        passed = bool(datasets) and all(dataset.get("validation_status") in {"passed", "passed_with_limitations"} for dataset in datasets)
        return {"overall_pass": passed, "checks": ["source_metadata", "dataset_validation_status"], "validated_at": now}
    if stage == "ANALYZE":
        return {"claims": [], "methodology": "mock execution only", "limitations": ["No real data used"]}
    if stage == "REVIEW":
        return {"passed": True, "findings": [], "reviewer": "mock_claude_code"}
    if stage == "DELIVER":
        return {"report_path": "report.md", "evidence_bundle": ".", "delivered": True}
    return {"recorded": True, "summary_path": "report.md"}


def prompt(stage: str, task: dict[str, Any], artifact_name: str) -> str:
    return (
        f"You are the {ROLE_BY_STAGE[stage]} executor in an evidence-gated finance research pipeline. "
        f"Research question: {task['research_question']}. As-of date: {task['as_of_date']}. "
        f"Return ONLY valid JSON for {artifact_name}. Do not fabricate facts. If evidence is missing, "
        f"return the required shape but make the gate fail or state limitations explicitly. "
        f"Required JSON keys are {list(REQUIRED_FIELDS[stage])}; include every key even when declining."
    )


def real_call(role: str, request: str, cwd: Path) -> tuple[dict[str, Any], str]:
    if role == "codex":
        command = ["ssh", "hk43", "codex", "exec", "--ephemeral", "--sandbox", "read-only", "-"]
    elif role == "claude_code":
        command = ["claude", "--safe-mode", "--print", "--output-format", "json", "--permission-mode", "plan", request]
        request = ""
    elif role == "hermescold":
        command = ["ssh", "hk43", "/home/ubuntu/.local/bin/hermescold-pipeline-worker.py"]
        request = json.dumps({"prompt": request})
    else:
        raise ValueError(f"No safe automatic executor configured for role: {role}")
    result = subprocess.run(command, input=request, text=True, capture_output=True, cwd=cwd, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"{role} failed with {result.returncode}")
    output = result.stdout.strip()
    if role == "claude_code":
        output = json.loads(output).get("result", "")
    try:
        return json.loads(output), output
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", output, re.S)
        if not match:
            raise RuntimeError(f"{role} did not return a JSON artifact")
        return json.loads(match.group(1)), output


def dispatch(root: Path, run_id: str, execute: bool) -> dict[str, Any]:
    controller = ResearchController(root)
    state = controller.load_state(run_id)
    if state["status"] in {"DONE", "FAILED_GATES", "BLOCKED_DATA_INVALID", "BLOCKED_DATA_UNAVAILABLE", "BLOCKED_HUMAN_DECISION_REQUIRED"}:
        return state
    stage = state["current_stage"]
    task = read_json(controller.run_dir(run_id) / "task.json") or {}
    task["_run_dir"] = str(controller.run_dir(run_id))
    artifact_name = controller.required_artifact(stage)
    job_input = json.dumps({"stage": stage, "task": task}, sort_keys=True)
    fingerprint = hashlib.sha256(job_input.encode()).hexdigest()
    receipt_path = controller.run_dir(run_id) / "dispatch" / f"{stage.lower()}.json"
    prior = read_json(receipt_path)
    if prior and prior.get("fingerprint") == fingerprint and prior.get("status") == "succeeded":
        return controller.advance(run_id)
    role = ROLE_BY_STAGE[stage]
    try:
        if execute and role in {"codex", "claude_code", "hermescold"}:
            artifact, raw = real_call(role, prompt(stage, task, artifact_name), root)
            mode = "real"
        elif execute and role == "deterministic":
            artifact, raw, mode = artifact_for(stage, task), "deterministic", "deterministic"
        elif execute:
            raise RuntimeError(f"No executor configured for role: {role}")
        else:
            artifact, raw, mode = artifact_for(stage, task), "mock", "mock"
        if not isinstance(artifact, dict) or any(key not in artifact for key in REQUIRED_FIELDS[stage]):
            raise RuntimeError(f"{role} returned an invalid {artifact_name} contract; required keys: {REQUIRED_FIELDS[stage]}")
        if stage == "DELIVER":
            (controller.run_dir(run_id) / "report.md").write_text(raw + "\n")
        write_json(controller.run_dir(run_id) / artifact_name, artifact)
        write_json(receipt_path, {"at": utc_now(), "stage": stage, "role": role, "mode": mode, "fingerprint": fingerprint, "recovery_attempt": state.get("recovery_attempts", {}).get(stage, 0), "status": "succeeded", "raw_response": raw[:4000]})
        return controller.advance(run_id)
    except Exception as error:
        write_json(receipt_path, {"at": utc_now(), "stage": stage, "role": role, "fingerprint": fingerprint, "recovery_attempt": state.get("recovery_attempts", {}).get(stage, 0), "status": "failed", "error": str(error)})
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--execute", action="store_true", help="Use configured live agent adapters instead of deterministic mocks")
    parser.add_argument("run_id")
    args = parser.parse_args()
    print(json.dumps(dispatch(args.root, args.run_id, args.execute), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
