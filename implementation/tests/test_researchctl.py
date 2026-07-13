import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE = Path(__file__).parents[1] / "scripts" / "researchctl.py"
sys.path.insert(0, str(MODULE.parent))
SPEC = importlib.util.spec_from_file_location("researchctl", MODULE)
researchctl = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(researchctl)

DISPATCH_SPEC = importlib.util.spec_from_file_location("stage_dispatch", Path(__file__).parents[1] / "scripts" / "stage_dispatch.py")
stage_dispatch = importlib.util.module_from_spec(DISPATCH_SPEC)
assert DISPATCH_SPEC.loader
DISPATCH_SPEC.loader.exec_module(stage_dispatch)


def write_artifact(run_dir: Path, name: str, content: dict) -> None:
    (run_dir / name).write_text(json.dumps(content))


class ResearchControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "config").mkdir()
        (self.root / "config" / "controller.json").write_text(json.dumps({"stage_timeout_seconds": 1, "max_recovery_attempts": 2}))
        self.controller = researchctl.ResearchController(self.root)
        self.run_id = self.controller.create("Test an evidence-gated research run", "deep_research", "test", "2026-07-12")
        self.run_dir = self.root / "runs" / self.run_id

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def advance_with_happy_artifacts(self) -> None:
        write_artifact(self.run_dir, "qualification.json", {"qualified": True, "data_routes": ["fmdata"], "methodology_risk": "low"})
        self.controller.advance(self.run_id)
        write_artifact(self.run_dir, "plan.json", {"research_question": "q", "hypotheses": [], "data_requests": [], "validation_plan": [], "review_plan": []})
        self.controller.advance(self.run_id)
        write_artifact(self.run_dir, "data_manifest.json", {"datasets": [{"dataset_id": "d1", "source_system": "test", "source_name": "test", "retrieved_at": "2026-07-12T00:00:00Z", "validation_status": "pending"}], "retrieved_at": "2026-07-12T00:00:00Z"})
        self.controller.advance(self.run_id)
        write_artifact(self.run_dir, "data_validation.json", {"overall_pass": True, "checks": [], "validated_at": "2026-07-12T00:00:00Z"})
        self.controller.advance(self.run_id)
        write_artifact(self.run_dir, "analysis.json", {"claims": [], "methodology": "test", "limitations": []})
        self.controller.advance(self.run_id)
        write_artifact(self.run_dir, "review.json", {"passed": True, "findings": [], "reviewer": "claude_code"})
        self.controller.advance(self.run_id)
        (self.run_dir / "report.md").write_text("report")
        write_artifact(self.run_dir, "delivery.json", {"report_path": "report.md", "evidence_bundle": ".", "delivered": True})
        self.controller.advance(self.run_id)
        write_artifact(self.run_dir, "record.json", {"recorded": True, "summary_path": "report.md"})

    def test_happy_path_reaches_done(self) -> None:
        self.advance_with_happy_artifacts()
        state = self.controller.advance(self.run_id)
        self.assertEqual(state["status"], "DONE")

    def test_failed_validation_blocks(self) -> None:
        write_artifact(self.run_dir, "qualification.json", {"qualified": True, "data_routes": ["fmdata"], "methodology_risk": "low"})
        self.controller.advance(self.run_id)
        write_artifact(self.run_dir, "plan.json", {"research_question": "q", "hypotheses": [], "data_requests": [], "validation_plan": [], "review_plan": []})
        self.controller.advance(self.run_id)
        write_artifact(self.run_dir, "data_manifest.json", {"datasets": [{"dataset_id": "d1", "source_system": "test", "source_name": "test", "retrieved_at": "2026-07-12T00:00:00Z", "validation_status": "pending"}], "retrieved_at": "2026-07-12T00:00:00Z"})
        self.controller.advance(self.run_id)
        write_artifact(self.run_dir, "data_validation.json", {"overall_pass": False, "checks": ["freshness"], "validated_at": "2026-07-12T00:00:00Z"})
        state = self.controller.advance(self.run_id)
        self.assertEqual(state["status"], "BLOCKED_DATA_INVALID")

    def test_stalled_run_retries_then_escalates(self) -> None:
        state = self.controller.load_state(self.run_id)
        state["stage_started_at"] = "2000-01-01T00:00:00Z"
        self.controller.save_state(self.run_id, state)
        self.assertEqual(self.controller.watch_run(self.run_id, stale_after_seconds=1)["status"], "INTAKE")
        self.assertEqual(self.controller.watch_run(self.run_id, stale_after_seconds=1)["status"], "INTAKE")
        state = self.controller.watch_run(self.run_id, stale_after_seconds=1)
        self.assertEqual(state["status"], "BLOCKED_HUMAN_DECISION_REQUIRED")
        self.assertTrue(any(event["kind"] == "ESCALATED" for event in state["events"]))
        self.assertTrue((self.run_dir / "alert.json").is_file())

    def test_alert_can_be_marked_delivered(self) -> None:
        state = self.controller.load_state(self.run_id)
        self.controller.raise_alert(self.run_id, state, "test")
        self.controller.mark_alert_delivered(self.run_id)
        self.assertIsNotNone(json.loads((self.run_dir / "alert.json").read_text())["delivered_at"])

    def test_mock_dispatch_completes_all_stages(self) -> None:
        for _ in range(8):
            stage_dispatch.dispatch(self.root, self.run_id, execute=False)
        self.assertEqual(self.controller.status(self.run_id)["status"], "DONE")
        self.assertTrue((self.run_dir / "dispatch" / "review.json").is_file())

    def test_dispatch_prompt_declares_required_contract(self) -> None:
        task = json.loads((self.run_dir / "task.json").read_text())
        self.assertIn("data_routes", stage_dispatch.prompt("QUALIFY", task, "qualification.json"))

    def test_real_claude_command_needs_no_remote_schema_path(self) -> None:
        source = (Path(__file__).parents[1] / "scripts" / "stage_dispatch.py").read_text()
        self.assertNotIn("schema_path.read_text", source)


if __name__ == "__main__":
    unittest.main()
