#!/usr/bin/env python3
"""Dispatch each active run once, then only after a bounded watchdog recovery."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from researchctl import ResearchController, TERMINAL_STATUSES, read_json
from stage_dispatch import dispatch


def should_dispatch(controller: ResearchController, run_id: str) -> bool:
    state = controller.load_state(run_id)
    if state["status"] in TERMINAL_STATUSES:
        return False
    stage = state["current_stage"]
    receipt = read_json(controller.run_dir(run_id) / "dispatch" / f"{stage.lower()}.json")
    if not receipt:
        return True
    return receipt.get("status") == "failed" and int(receipt.get("recovery_attempt", 0)) < int(state.get("recovery_attempts", {}).get(stage, 0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    controller = ResearchController(args.root)
    results = []
    for state_path in sorted(controller.runs_dir.glob("*/state.json")):
        run_id = state_path.parent.name
        if should_dispatch(controller, run_id):
            try:
                results.append({"run_id": run_id, "state": dispatch(args.root, run_id, execute=True)})
            except Exception as error:
                results.append({"run_id": run_id, "error": str(error)})
    print(json.dumps(results, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
