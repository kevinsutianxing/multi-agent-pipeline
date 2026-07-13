from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from reliable_pipeline import ReliablePipeline, STAGES  # noqa: E402


def artifact(stage: str, question: str = "test question") -> dict:
    values = {
        "QUALIFY": {
            "qualified": True,
            "research_question": question,
            "scope": ["company"],
            "risks": [],
            "evidence": [],
        },
        "ACQUIRE": {
            "datasets": [
                {
                    "dataset_id": "d1",
                    "source_name": "primary",
                    "source_ref": "file:test",
                    "retrieved_at": "2026-07-13T00:00:00Z",
                    "observations": [{"value": 1}],
                    "validation_status": "passed",
                }
            ],
            "limitations": [],
            "evidence": [{"dataset_id": "d1"}],
        },
        "VALIDATE": {
            "overall_pass": True,
            "checks": [{"passed": True}],
            "limitations": [],
            "evidence": [{"kind": "deterministic"}],
        },
        "ANALYZE": {
            "claims": [{"claim_text": "one", "evidence_refs": ["d1"]}],
            "methodology": "test",
            "limitations": [],
            "evidence": [{"dataset_id": "d1"}],
        },
        "REVIEW": {
            "passed": True,
            "findings": [],
            "evidence": [{"stage": "ANALYZE"}],
        },
        "DELIVER": {
            "executive_summary": "summary",
            "report_markdown": "# Report\n\nEvidence-backed result.",
            "evidence": [{"dataset_id": "d1"}],
        },
    }[stage]
    return {"stage": stage, **values}


class ReliablePipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db = root / "state" / "pipeline.db"
        self.runs = root / "runs"
        self.pipeline = ReliablePipeline(self.db, max_attempts=2, runs_dir=self.runs)
        self.run_id = self.pipeline.create(
            "request-1",
            "test question",
            requester="test",
            notify_target="feishu:chat-1",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def claim(self, worker: str = "worker-1", lease_seconds: int = 1200) -> dict:
        job = self.pipeline.claim(worker, lease_seconds=lease_seconds)
        self.assertIsNotNone(job)
        return job

    def submit(self, stage: str, value: dict | None = None, worker: str = "worker-1") -> dict:
        job = self.claim(worker)
        self.assertEqual(job["stage"], stage)
        return self.pipeline.finish(job["id"], worker, json.dumps(value or artifact(stage)), exit_code=0)

    def test_duplicate_request_is_idempotent(self) -> None:
        again = self.pipeline.create("request-1", "different question")
        self.assertEqual(again, self.run_id)

    def test_claim_contains_question_and_prior_artifacts(self) -> None:
        first = self.claim()
        self.assertEqual(first["context"]["question"], "test question")
        self.pipeline.finish(first["id"], "worker-1", json.dumps(artifact("QUALIFY")))
        second = self.claim("worker-2")
        self.assertIn("QUALIFY", second["context"]["prior_artifacts"])
        self.assertTrue(second["context"]["prior_artifacts"]["QUALIFY"]["qualified"])

    def test_normalizer_accepts_fence_preface_and_wrapped_result(self) -> None:
        value = artifact("QUALIFY")
        parsed, error = self.pipeline.normalize_and_validate("QUALIFY", f"Here is the result:\n```json\n{json.dumps(value)}\n```")
        self.assertIsNone(error)
        self.assertEqual(parsed, value)
        wrapped = json.dumps({"result": f"prefix {json.dumps(value)} suffix"})
        parsed, error = self.pipeline.normalize_and_validate("QUALIFY", wrapped)
        self.assertIsNone(error)
        self.assertEqual(parsed, value)
        noisy = '{"tool":"search","status":"ok"}\n' + json.dumps(value)
        parsed, error = self.pipeline.normalize_and_validate("QUALIFY", noisy)
        self.assertIsNone(error)
        self.assertEqual(parsed, value)

    def test_full_run_completes_and_persists_report(self) -> None:
        for stage in STAGES:
            result = self.submit(stage)
        self.assertEqual(result["status"], "DONE")
        status = self.pipeline.status(self.run_id)
        self.assertEqual(status["run"]["status"], "DONE")
        report = self.runs / self.run_id / "report.md"
        self.assertTrue(report.is_file())
        self.assertIn("Evidence-backed", report.read_text())
        self.assertTrue((self.runs / self.run_id / "artifacts" / "analyze.json").is_file())
        self.assertTrue((self.runs / self.run_id / "raw" / "deliver.txt").is_file())

    def test_invalid_output_retries_then_blocks(self) -> None:
        for index in range(2):
            worker = f"w-{index}"
            job = self.claim(worker)
            result = self.pipeline.finish(job["id"], worker, "not json")
        self.assertIn("no JSON", result["error"])
        self.assertEqual(self.pipeline.status(self.run_id)["run"]["status"], "BLOCKED")

    def test_negative_gate_blocks_without_advancing(self) -> None:
        rejected = artifact("QUALIFY")
        rejected["qualified"] = False
        result = self.submit("QUALIFY", rejected)
        self.assertEqual(result["status"], "BLOCKED")
        state = self.pipeline.status(self.run_id)
        self.assertEqual(state["run"]["stage"], "QUALIFY")
        self.assertEqual(state["run"]["status"], "BLOCKED")

    def test_lease_prevents_double_claim_and_rejects_stale_finish(self) -> None:
        first = self.claim("worker-a", lease_seconds=60)
        self.assertIsNone(self.pipeline.claim("worker-b", lease_seconds=60))
        with self.pipeline.db() as connection:
            connection.execute("UPDATE jobs SET lease_until='2000-01-01T00:00:00Z' WHERE id=?", (first["id"],))
        second = self.claim("worker-b", lease_seconds=60)
        self.assertEqual(second["id"], first["id"])
        stale = self.pipeline.finish(first["id"], "worker-a", json.dumps(artifact("QUALIFY")))
        self.assertEqual(stale["reason"], "stale_worker")
        accepted = self.pipeline.finish(second["id"], "worker-b", json.dumps(artifact("QUALIFY")))
        self.assertTrue(accepted["accepted"])

    def test_retry_reopens_blocked_stage(self) -> None:
        rejected = artifact("QUALIFY")
        rejected["qualified"] = False
        self.submit("QUALIFY", rejected)
        retried = self.pipeline.retry(self.run_id)
        self.assertEqual(retried["run"]["status"], "ACTIVE")
        job = self.claim("retry-worker")
        self.assertEqual(job["stage"], "QUALIFY")

    def test_notifications_are_targeted_and_durable(self) -> None:
        self.submit("QUALIFY")
        pending = self.pipeline.pending_notifications()
        self.assertEqual(len(pending), 1)
        payload = json.loads(pending[0]["payload"])
        self.assertEqual(payload["target"], "feishu:chat-1")
        self.pipeline.mark_notification(pending[0]["run_id"], pending[0]["kind"], error="temporary")
        self.assertEqual(len(self.pipeline.pending_notifications()), 1)
        self.pipeline.mark_notification(pending[0]["run_id"], pending[0]["kind"])
        self.assertEqual(self.pipeline.pending_notifications(), [])

    def test_legacy_database_is_migrated(self) -> None:
        legacy = Path(self.temp.name) / "legacy.db"
        connection = sqlite3.connect(legacy)
        connection.executescript(
            """
            CREATE TABLE runs (id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, question TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE jobs (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, lease_until TEXT, error TEXT, UNIQUE(run_id,stage));
            CREATE TABLE attempts (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, exit_code INTEGER, raw_output TEXT, error TEXT);
            CREATE TABLE artifacts (run_id TEXT NOT NULL, stage TEXT NOT NULL, raw_output TEXT NOT NULL, normalized TEXT, valid INTEGER NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(run_id,stage));
            CREATE TABLE notifications (run_id TEXT NOT NULL, kind TEXT NOT NULL, sent_at TEXT, PRIMARY KEY(run_id,kind));
            CREATE TABLE events (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
            """
        )
        connection.execute("INSERT INTO runs VALUES ('r','k','q','ACTIVE','QUALIFY','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')")
        connection.execute("INSERT INTO jobs VALUES ('j','r','QUALIFY','RUNNING',1,NULL,NULL)")
        connection.execute("INSERT INTO notifications VALUES ('r','EVENT:old',NULL)")
        connection.commit()
        connection.close()
        migrated = ReliablePipeline(legacy)
        health = migrated.health()
        self.assertTrue(health["ok"])
        with migrated.db() as db:
            self.assertIn("notify_target", {row[1] for row in db.execute("PRAGMA table_info(runs)")})
            self.assertIn("worker_id", {row[1] for row in db.execute("PRAGMA table_info(jobs)")})
            self.assertEqual(db.execute("SELECT status FROM jobs WHERE id='j'").fetchone()[0], "PENDING")
            self.assertIsNotNone(db.execute("SELECT sent_at FROM notifications WHERE run_id='r'").fetchone()[0])


class WorkerIntegrationTest(unittest.TestCase):
    def test_worker_drives_full_fake_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "pipeline.db"
            runs = root / "runs"
            pipeline = ReliablePipeline(db, runs_dir=runs)
            run_id = pipeline.create("worker-e2e", "worker question")
            fake = root / "fake_adapter.py"
            fake.write_text(
                "import json,sys\n"
                "req=json.loads(sys.stdin.read())\n"
                f"values={repr({stage: artifact(stage) for stage in STAGES})}\n"
                "print(json.dumps(values[req['stage']]))\n"
            )
            worker = SCRIPTS / "reliable_worker.py"
            for _ in STAGES:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(worker),
                        "--db",
                        str(db),
                        "--runs-dir",
                        str(runs),
                        "--timeout",
                        "20",
                        "--heartbeat-seconds",
                        "1",
                        "--command",
                        sys.executable,
                        str(fake),
                    ],
                    text=True,
                    capture_output=True,
                    env={**os.environ, "PYTHONPATH": str(SCRIPTS)},
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(pipeline.status(run_id)["run"]["status"], "DONE")
            self.assertTrue((runs / run_id / "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
