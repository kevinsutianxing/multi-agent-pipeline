#!/usr/bin/env python3
"""External state controller for Codex-led financial research runs.

Agents create declared artifacts. This controller verifies artifact presence,
runs deterministic gates, records state transitions, and applies the two-key
release rule. It does not call an LLM and does not accept prose as a gate result.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

STATE_FILE = "run_state.json"

CHECKPOINT_REQUIREMENTS = {
    "PLANNED": ("research_brief.json", "research_plan.json"),
    "ACQUIRED": (
        "source_manifest.data.json",
        "source_manifest.research.json",
        "dataset_manifest.json",
    ),
    "ANALYZED": ("calculation_manifest.json", "claim_ledger.jsonl"),
    "REPRODUCED": ("reproducibility_report.json",),
}

ALLOWED_PREVIOUS = {
    "PLANNED": {"INTAKE"},
    "ACQUIRED": {"DEERFLOW_READY"},
    "ANALYZED": {"DATA_VALIDATED"},
    "REPRODUCED": {"ANALYZED"},
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"required file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_state(run_dir: Path) -> dict[str, Any]:
    return read_json(run_dir / STATE_FILE)


def record_transition(
    run_dir: Path,
    state: dict[str, Any],
    target: str,
    reason: str,
    artifacts: list[str] | None = None,
) -> dict[str, Any]:
    previous = str(state.get("state") or "UNKNOWN")
    event = {
        "at": now_iso(),
        "from": previous,
        "to": target,
        "reason": reason,
        "artifacts": artifacts or [],
    }
    state["state"] = target
    state["updated_at"] = event["at"]
    state.setdefault("history", []).append(event)
    write_json(run_dir / STATE_FILE, state)
    return state


def require_files(run_dir: Path, filenames: tuple[str, ...]) -> list[str]:
    missing = [name for name in filenames if not (run_dir / name).is_file()]
    if missing:
        raise ValueError(f"missing required artifacts: {', '.join(missing)}")
    return list(filenames)


def run_command(command: list[str], cwd: Path) -> int:
    completed = subprocess.run(command, cwd=cwd, check=False)
    return int(completed.returncode)


def read_report_or_block(
    run_dir: Path,
    state: dict[str, Any],
    report_path: Path,
    *,
    blocked_state: str,
    reason: str,
) -> dict[str, Any] | None:
    try:
        return read_json(report_path)
    except ValueError as exc:
        artifacts = [report_path.name] if report_path.exists() else []
        record_transition(
            run_dir,
            state,
            blocked_state,
            f"{reason}: {exc}",
            artifacts,
        )
        return None


def build_deerflow_preflight_command(
    repo_root: Path,
    report_path: Path,
    inputs: dict[str, Any],
) -> list[str]:
    command = [
        sys.executable,
        str(repo_root / "scripts" / "deerflow_preflight.py"),
        "--deployment-manifest",
        str(inputs["deployment_manifest"]),
        "--extensions-config",
        str(inputs["extensions_config"]),
        "--report",
        str(report_path),
    ]
    config_path = inputs.get("config")
    if config_path:
        command.extend(["--config", str(config_path)])
    if inputs.get("skip_live_agent_inventory") is True:
        command.append("--skip-live-agent-inventory")
    return command


def init_run(args: argparse.Namespace) -> int:
    run_dir = args.run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / STATE_FILE
    if state_path.exists() and not args.force:
        raise ValueError(f"state already exists: {state_path}; use --force to replace")

    as_of = args.as_of.isoformat()
    brief = {
        "run_id": args.run_id,
        "topic": args.topic,
        "research_type": args.research_type,
        "as_of": as_of,
        "created_at": now_iso(),
    }
    state = {
        "version": 1,
        "run_id": args.run_id,
        "as_of": as_of,
        "research_type": args.research_type,
        "state": "INTAKE",
        "attempts": {},
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "history": [],
    }
    write_json(run_dir / "research_brief.json", brief)
    write_json(state_path, state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def checkpoint(args: argparse.Namespace) -> int:
    run_dir = args.run_dir.resolve()
    state = load_state(run_dir)
    target = args.phase
    current = str(state.get("state"))
    allowed = ALLOWED_PREVIOUS[target]
    if current not in allowed:
        raise ValueError(
            f"cannot checkpoint {target} from {current}; "
            f"allowed previous states: {sorted(allowed)}"
        )
    artifacts = require_files(run_dir, CHECKPOINT_REQUIREMENTS[target])
    if target == "REPRODUCED":
        report = read_json(run_dir / "reproducibility_report.json")
        if report.get("status") != "PASS":
            record_transition(
                run_dir,
                state,
                "BLOCKED_METHOD",
                "reproducibility report did not pass",
            )
            return 1
    state = record_transition(
        run_dir,
        state,
        target,
        f"{target} artifacts verified",
        artifacts,
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def deerflow_preflight(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    run_dir = args.run_dir.resolve()
    state = load_state(run_dir)
    current = state.get("state")
    if current not in {"PLANNED", "BLOCKED_EXTERNAL"}:
        raise ValueError(
            "DeerFlow preflight requires PLANNED or BLOCKED_EXTERNAL, "
            f"got {current}"
        )

    inputs = {
        "deployment_manifest": str(args.deployment_manifest.resolve()),
        "extensions_config": str(args.extensions_config.resolve()),
        "config": str(args.config.resolve()) if args.config is not None else None,
        "skip_live_agent_inventory": bool(args.skip_live_agent_inventory),
    }
    report_path = run_dir / "deerflow_preflight_report.json"
    rc = run_command(
        build_deerflow_preflight_command(repo_root, report_path, inputs),
        repo_root,
    )
    report = read_report_or_block(
        run_dir,
        state,
        report_path,
        blocked_state="BLOCKED_EXTERNAL",
        reason="official DeerFlow deployment preflight produced no valid report",
    )
    if report is None:
        return 1
    if rc != 0 or report.get("status") != "PASS":
        record_transition(
            run_dir,
            state,
            "BLOCKED_EXTERNAL",
            "official DeerFlow deployment preflight failed",
            [report_path.name],
        )
        return 1

    state["deerflow_preflight_inputs"] = inputs
    state = record_transition(
        run_dir,
        state,
        "DEERFLOW_READY",
        "official DeerFlow deployment preflight passed",
        [report_path.name],
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def gate(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    run_dir = args.run_dir.resolve()
    state = load_state(run_dir)
    stage = args.stage
    expected_state = "ACQUIRED" if stage == "acquisition" else "REPRODUCED"
    if state.get("state") != expected_state:
        raise ValueError(
            f"{stage} gate requires state {expected_state}, "
            f"got {state.get('state')}"
        )

    if stage == "acquisition":
        merge_rc = run_command(
            [
                sys.executable,
                str(repo_root / "scripts" / "merge_manifests.py"),
                "--run-dir",
                str(run_dir),
            ],
            repo_root,
        )
        if merge_rc != 0:
            record_transition(
                run_dir,
                state,
                "BLOCKED_DATA",
                "source manifest merge failed",
            )
            return 1
        report_path = run_dir / "acquisition_gate_report.json"
        success_state = "DATA_VALIDATED"
    else:
        report_path = run_dir / "release_data_gate_report.json"
        success_state = "RELEASE_DATA_VALIDATED"

    command = [
        sys.executable,
        str(repo_root / "scripts" / "validate_evidence.py"),
        "--run-dir",
        str(run_dir),
        "--as-of",
        str(state["as_of"]),
        "--stage",
        stage,
        "--report",
        str(report_path),
    ]
    rc = run_command(command, repo_root)
    report = read_report_or_block(
        run_dir,
        state,
        report_path,
        blocked_state="BLOCKED_DATA",
        reason=f"{stage} evidence gate produced no valid report",
    )
    if report is None:
        return 1
    if rc != 0 or report.get("status") != "PASS":
        record_transition(
            run_dir,
            state,
            "BLOCKED_DATA",
            f"{stage} evidence gate failed",
            [report_path.name],
        )
        return 1

    state = record_transition(
        run_dir,
        state,
        success_state,
        f"{stage} evidence gate passed",
        [report_path.name],
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def record_review(args: argparse.Namespace) -> int:
    run_dir = args.run_dir.resolve()
    state = load_state(run_dir)
    if state.get("state") != "RELEASE_DATA_VALIDATED":
        raise ValueError(
            "review requires RELEASE_DATA_VALIDATED, "
            f"got {state.get('state')}"
        )
    report_path = run_dir / "review_report.json"
    report = read_json(report_path)
    status = report.get("status")
    critical = report.get("critical_count")
    if status == "NEEDS_HUMAN":
        record_transition(
            run_dir,
            state,
            "NEEDS_HUMAN",
            "independent reviewer requested human decision",
            [report_path.name],
        )
        return 1
    if status != "PASS" or not isinstance(critical, int) or critical != 0:
        record_transition(
            run_dir,
            state,
            "BLOCKED_METHOD",
            "independent review failed",
            [report_path.name],
        )
        return 1
    state = record_transition(
        run_dir,
        state,
        "REVIEWED",
        "independent review passed",
        [report_path.name],
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def rerun_deerflow_preflight_for_release(
    repo_root: Path,
    run_dir: Path,
    state: dict[str, Any],
) -> bool:
    inputs = state.get("deerflow_preflight_inputs")
    if not isinstance(inputs, dict):
        record_transition(
            run_dir,
            state,
            "BLOCKED_EXTERNAL",
            "release cannot reproduce DeerFlow preflight: inputs missing from run state",
        )
        return False

    report_path = run_dir / "deerflow_release_preflight_report.json"
    rc = run_command(
        build_deerflow_preflight_command(repo_root, report_path, inputs),
        repo_root,
    )
    report = read_report_or_block(
        run_dir,
        state,
        report_path,
        blocked_state="BLOCKED_EXTERNAL",
        reason="release DeerFlow preflight produced no valid report",
    )
    if report is None:
        return False
    if rc != 0 or report.get("status") != "PASS":
        record_transition(
            run_dir,
            state,
            "BLOCKED_EXTERNAL",
            "release DeerFlow deployment preflight failed",
            [report_path.name],
        )
        return False
    return True


def release(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    run_dir = args.run_dir.resolve()
    state = load_state(run_dir)
    if state.get("state") != "REVIEWED":
        raise ValueError(f"release requires REVIEWED, got {state.get('state')}")

    if not rerun_deerflow_preflight_for_release(repo_root, run_dir, state):
        return 1

    report_states = {
        "deerflow_preflight_report.json": "BLOCKED_EXTERNAL",
        "deerflow_release_preflight_report.json": "BLOCKED_EXTERNAL",
        "acquisition_gate_report.json": "BLOCKED_DATA",
        "release_data_gate_report.json": "BLOCKED_DATA",
        "reproducibility_report.json": "BLOCKED_METHOD",
        "review_report.json": "BLOCKED_METHOD",
    }
    required_reports = tuple(report_states)
    require_files(run_dir, required_reports)
    for filename, blocked_state in report_states.items():
        report = read_json(run_dir / filename)
        if report.get("status") != "PASS":
            record_transition(
                run_dir,
                state,
                blocked_state,
                f"{filename} is not PASS",
                [filename],
            )
            return 1

    release_requirements_path = run_dir / "release_requirements.json"
    if release_requirements_path.exists():
        requirements = read_json(release_requirements_path)
        sensitive = any(
            requirements.get(flag) is True
            for flag in (
                "methodology_changed",
                "investment_recommendation",
                "material_source_conflict",
                "proxy_substitution_affects_conclusion",
            )
        )
        if sensitive and requirements.get("human_approved") is not True:
            record_transition(
                run_dir,
                state,
                "NEEDS_HUMAN",
                "release requires explicit human approval",
                [release_requirements_path.name],
            )
            return 1

    candidate = Path(args.candidate)
    candidate_path = candidate if candidate.is_absolute() else run_dir / candidate
    if not candidate_path.is_file():
        raise ValueError(f"candidate deliverable is missing: {candidate_path}")

    state = record_transition(
        run_dir,
        state,
        "COMPLETED",
        "two-key release gate passed",
        [candidate_path.name, *required_reports],
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def status(args: argparse.Namespace) -> int:
    state = load_state(args.run_dir.resolve())
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control a financial research run")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--run-dir", required=True, type=Path)
    init_parser.add_argument("--run-id", required=True)
    init_parser.add_argument("--topic", required=True)
    init_parser.add_argument(
        "--research-type",
        required=True,
        choices=("quant", "industry", "company", "mixed"),
    )
    init_parser.add_argument("--as-of", required=True, type=dt.date.fromisoformat)
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(func=init_run)

    checkpoint_parser = subparsers.add_parser("checkpoint")
    checkpoint_parser.add_argument("--run-dir", required=True, type=Path)
    checkpoint_parser.add_argument(
        "--phase",
        required=True,
        choices=tuple(CHECKPOINT_REQUIREMENTS),
    )
    checkpoint_parser.set_defaults(func=checkpoint)

    preflight_parser = subparsers.add_parser("deerflow-preflight")
    preflight_parser.add_argument("--run-dir", required=True, type=Path)
    preflight_parser.add_argument("--deployment-manifest", required=True, type=Path)
    preflight_parser.add_argument("--extensions-config", required=True, type=Path)
    preflight_parser.add_argument("--config", type=Path)
    preflight_parser.add_argument("--skip-live-agent-inventory", action="store_true")
    preflight_parser.set_defaults(func=deerflow_preflight)

    gate_parser = subparsers.add_parser("gate")
    gate_parser.add_argument("--run-dir", required=True, type=Path)
    gate_parser.add_argument(
        "--stage",
        required=True,
        choices=("acquisition", "release"),
    )
    gate_parser.set_defaults(func=gate)

    review_parser = subparsers.add_parser("review")
    review_parser.add_argument("--run-dir", required=True, type=Path)
    review_parser.set_defaults(func=record_review)

    release_parser = subparsers.add_parser("release")
    release_parser.add_argument("--run-dir", required=True, type=Path)
    release_parser.add_argument("--candidate", required=True)
    release_parser.set_defaults(func=release)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--run-dir", required=True, type=Path)
    status_parser.set_defaults(func=status)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
