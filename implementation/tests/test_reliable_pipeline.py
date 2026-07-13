import json
import tempfile
import unittest
from pathlib import Path
import sys
import subprocess

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from reliable_pipeline import ReliablePipeline


class ReliablePipelineTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.pipeline = ReliablePipeline(Path(self.directory.name) / "queue.db")
        self.run_id = self.pipeline.create("message-1", "test")

    def tearDown(self): self.directory.cleanup()

    def test_duplicate_message_is_idempotent(self): self.assertEqual(self.run_id, self.pipeline.create("message-1", "other"))

    def test_stage_events_are_durable_notifications(self):
        with self.pipeline.db() as db:
            self.assertEqual(db.execute("SELECT kind FROM events WHERE run_id=?", (self.run_id,)).fetchone()[0], "RUN_CREATED")
        self.assertEqual(len(self.pipeline.pending_notifications()), 1)

    def test_invalid_output_retries_then_blocks(self):
        for _ in range(2):
            job = self.pipeline.claim(); self.pipeline.finish(job["id"], "not json")
        with self.pipeline.db() as db: self.assertEqual(db.execute("SELECT status FROM runs WHERE id=?", (self.run_id,)).fetchone()[0], "BLOCKED")

    def test_crashed_worker_recovers(self):
        self.pipeline.claim(); self.pipeline.recover_running()
        self.assertIsNotNone(self.pipeline.claim())

    def test_valid_artifact_advances(self):
        job = self.pipeline.claim(); self.pipeline.finish(job["id"], json.dumps({"stage":"QUALIFY","evidence":[]}))
        with self.pipeline.db() as db: self.assertEqual(db.execute("SELECT stage FROM runs WHERE id=?", (self.run_id,)).fetchone()[0], "ACQUIRE")

    def test_notification_is_durable_until_marked_sent(self):
        for _ in range(2):
            job = self.pipeline.claim(); self.pipeline.finish(job["id"], "bad")
        for notification in self.pipeline.pending_notifications():
            self.pipeline.mark_notified(notification["run_id"], notification["kind"])
        self.assertEqual(self.pipeline.pending_notifications(), [])

    def test_command_worker_records_nonzero_exit_without_advancing(self):
        db_path = Path(self.directory.name) / "queue.db"
        result = subprocess.run([sys.executable, str(Path(__file__).parents[1] / "scripts" / "reliable_worker.py"), "--db", str(db_path), "--command", sys.executable, "-c", "import sys; sys.exit(9)"], env={**__import__('os').environ, "PYTHONPATH": str(Path(__file__).parents[1] / "scripts")})
        self.assertEqual(result.returncode, 9)
        with self.pipeline.db() as db:
            self.assertEqual(db.execute("SELECT stage FROM runs WHERE id=?", (self.run_id,)).fetchone()[0], "QUALIFY")
