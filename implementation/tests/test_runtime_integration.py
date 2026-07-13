from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from reliable_pipeline import ReliablePipeline  # noqa: E402


def qualification() -> dict:
    return {
        "stage": "QUALIFY",
        "qualified": True,
        "research_question": "q",
        "scope": [],
        "risks": [],
        "evidence": [],
    }


class AdapterTest(unittest.TestCase):
    def test_deterministic_validation_uses_acquired_manifest(self) -> None:
        request = {
            "stage": "VALIDATE",
            "context": {
                "stage": "VALIDATE",
                "question": "q",
                "prior_artifacts": {
                    "ACQUIRE": {
                        "datasets": [
                            {
                                "source_name": "filing",
                                "source_ref": "sec:1",
                                "retrieved_at": "2026-07-13T00:00:00Z",
                                "observations": [{"x": 1}],
                                "validation_status": "passed",
                            }
                        ],
                        "limitations": [],
                    }
                },
            },
        }
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "reliable_agent_adapter.py")],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            env={**os.environ, "PYTHONPATH": str(SCRIPTS)},
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        artifact = json.loads(result.stdout)
        self.assertTrue(artifact["overall_pass"])
        self.assertEqual(artifact["checks"][0]["source_identity"], True)

    def test_validation_fails_unverified_dataset(self) -> None:
        request = {
            "stage": "VALIDATE",
            "context": {
                "stage": "VALIDATE",
                "question": "q",
                "prior_artifacts": {
                    "ACQUIRE": {
                        "datasets": [
                            {
                                "source_name": "unknown",
                                "source_ref": "x",
                                "retrieved_at": "2026-07-13T00:00:00Z",
                                "observations": [{"x": 1}],
                                "validation_status": "unverified",
                            }
                        ],
                        "limitations": ["not verified"],
                    }
                },
            },
        }
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "reliable_agent_adapter.py")],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            env={**os.environ, "PYTHONPATH": str(SCRIPTS)},
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["overall_pass"])


class NotificationIntegrationTest(unittest.TestCase):
    def test_sender_receives_exact_target_and_success_is_durable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "pipeline.db"
            pipeline = ReliablePipeline(db, runs_dir=root / "runs")
            run_id = pipeline.create("n1", "q", notify_target="feishu:exact-chat")
            job = pipeline.claim("w")
            pipeline.finish(job["id"], "w", json.dumps(qualification()))
            capture = root / "capture.json"
            sender = root / "sender.py"
            sender.write_text(
                "import pathlib,sys\n"
                f"pathlib.Path({str(capture)!r}).write_text(sys.stdin.read())\n"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "reliable_notify.py"),
                    "--db",
                    str(db),
                    "--runs-dir",
                    str(root / "runs"),
                    "--command",
                    sys.executable,
                    str(sender),
                ],
                text=True,
                capture_output=True,
                env={**os.environ, "PYTHONPATH": str(SCRIPTS)},
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(capture.read_text())
            self.assertEqual(payload["target"], "feishu:exact-chat")
            self.assertEqual(payload["run_id"], run_id)
            self.assertEqual(pipeline.pending_notifications(), [])

    def test_failed_sender_leaves_outbox_pending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "pipeline.db"
            pipeline = ReliablePipeline(db)
            pipeline.create("n2", "q", notify_target="feishu:chat")
            job = pipeline.claim("w")
            pipeline.finish(job["id"], "w", json.dumps(qualification()))
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "reliable_notify.py"),
                    "--db",
                    str(db),
                    "--command",
                    sys.executable,
                    "-c",
                    "import sys; sys.exit(9)",
                ],
                text=True,
                capture_output=True,
                env={**os.environ, "PYTHONPATH": str(SCRIPTS)},
                timeout=20,
            )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(len(pipeline.pending_notifications()), 1)


class IngressPluginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = ROOT / "plugins" / "reliable_research_ingress" / "__init__.py"
        spec = importlib.util.spec_from_file_location("reliable_research_ingress", path)
        assert spec and spec.loader
        cls.plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.plugin)

    def event(self, text: str) -> object:
        platform = types.SimpleNamespace(value="feishu")
        source = types.SimpleNamespace(platform=platform, chat_id="chat-123")
        return types.SimpleNamespace(source=source, text=text, message_id="message-1")

    def test_non_trigger_is_ignored(self) -> None:
        self.assertIsNone(self.plugin.intercept(event=self.event("普通问题")))

    def test_trigger_uses_stdin_and_hard_skips_native_dispatch(self) -> None:
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            if command[0] == "ssh":
                return types.SimpleNamespace(returncode=0, stdout=json.dumps({"run_id": "run-1"}), stderr="")
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(self.plugin.subprocess, "run", side_effect=fake_run):
            result = self.plugin.intercept(event=self.event("启动多智能体研究：研究问题; rm -rf /"))
        self.assertEqual(result["action"], "skip")
        ssh_call = calls[0]
        self.assertEqual(ssh_call[1]["input"], "研究问题; rm -rf /")
        self.assertIn("--question-stdin", ssh_call[0][-1])
        self.assertIn("feishu:chat-123", ssh_call[0][-1])
        self.assertNotIn("研究问题; rm -rf /", ssh_call[0][-1])


if __name__ == "__main__":
    unittest.main()
