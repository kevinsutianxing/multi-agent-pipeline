#!/usr/bin/env python3
"""Durable, evidence-gated pipeline core. Workers never mutate run state."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator


STAGES = ("QUALIFY", "ACQUIRE", "VALIDATE", "ANALYZE", "REVIEW", "DELIVER")
TERMINAL = {"DONE", "BLOCKED", "FAILED"}


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ReliablePipeline:
    def __init__(self, db_path: Path, max_attempts: int = 2) -> None:
        self.db_path, self.max_attempts = db_path, max_attempts
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as connection:
            connection.executescript("""
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, question TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, lease_until TEXT, error TEXT, UNIQUE(run_id, stage));
            CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, exit_code INTEGER, raw_output TEXT, error TEXT);
            CREATE TABLE IF NOT EXISTS artifacts (run_id TEXT NOT NULL, stage TEXT NOT NULL, raw_output TEXT NOT NULL, normalized TEXT, valid INTEGER NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(run_id, stage));
            CREATE TABLE IF NOT EXISTS notifications (run_id TEXT NOT NULL, kind TEXT NOT NULL, sent_at TEXT, PRIMARY KEY(run_id, kind));
            CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
            """)

    @contextmanager
    def db(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def create(self, request_key: str, question: str) -> str:
        with self.db() as connection:
            existing = connection.execute("SELECT id FROM runs WHERE request_key=?", (request_key,)).fetchone()
            if existing:
                return str(existing["id"])
            run_id = uuid.uuid4().hex
            timestamp = now()
            connection.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?)", (run_id, request_key, question, "ACTIVE", STAGES[0], timestamp, timestamp))
            connection.execute("INSERT INTO jobs(id,run_id,stage,status) VALUES (?,?,?,?)", (uuid.uuid4().hex, run_id, STAGES[0], "PENDING"))
            self._event(connection, run_id, "RUN_CREATED", STAGES[0])
            return run_id

    def claim(self) -> sqlite3.Row | None:
        with self.db() as connection:
            job = connection.execute("SELECT * FROM jobs WHERE status='PENDING' ORDER BY rowid LIMIT 1").fetchone()
            if not job:
                return None
            connection.execute("UPDATE jobs SET status='RUNNING', attempts=attempts+1 WHERE id=?", (job["id"],))
            self._event(connection, job["run_id"], "JOB_STARTED", job["stage"])
            connection.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?)", (uuid.uuid4().hex, job["id"], now(), None, None, None, None))
            return connection.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone()

    def recover_running(self) -> None:
        with self.db() as connection:
            for job in connection.execute("SELECT * FROM jobs WHERE status='RUNNING'"):
                status = "PENDING" if job["attempts"] < self.max_attempts else "FAILED"
                connection.execute("UPDATE jobs SET status=?, error=? WHERE id=?", (status, "worker lost before completion", job["id"]))
                self._event(connection, job["run_id"], "JOB_RECOVERED", job["stage"])
                if status == "FAILED":
                    self._block(connection, job["run_id"], "worker exhausted retry budget")

    def finish(self, job_id: str, raw_output: str, exit_code: int = 0) -> None:
        with self.db() as connection:
            job = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job or job["status"] != "RUNNING":
                raise ValueError("job is not claimed")
            attempt = connection.execute("SELECT id FROM attempts WHERE job_id=? AND finished_at IS NULL", (job_id,)).fetchone()
            normalized, error = self._parse(job["stage"], raw_output) if exit_code == 0 else (None, "worker exited non-zero")
            connection.execute("UPDATE attempts SET finished_at=?, exit_code=?, raw_output=?, error=? WHERE id=?", (now(), exit_code, raw_output, error, attempt["id"]))
            connection.execute("INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?,?)", (job["run_id"], job["stage"], raw_output, json.dumps(normalized) if normalized else None, int(not error), now()))
            if error:
                status = "PENDING" if job["attempts"] < self.max_attempts else "FAILED"
                connection.execute("UPDATE jobs SET status=?, error=? WHERE id=?", (status, error, job_id))
                self._event(connection, job["run_id"], "JOB_RETRY" if status == "PENDING" else "JOB_FAILED", f"{job['stage']}: {error}")
                if status == "FAILED": self._block(connection, job["run_id"], error)
                return
            connection.execute("UPDATE jobs SET status='SUCCEEDED' WHERE id=?", (job_id,))
            self._event(connection, job["run_id"], "JOB_SUCCEEDED", job["stage"])
            index = STAGES.index(job["stage"])
            if index + 1 == len(STAGES):
                connection.execute("UPDATE runs SET status='DONE', updated_at=? WHERE id=?", (now(), job["run_id"]))
                self._event(connection, job["run_id"], "RUN_DONE", job["stage"])
            else:
                next_stage = STAGES[index + 1]
                connection.execute("UPDATE runs SET stage=?, updated_at=? WHERE id=?", (next_stage, now(), job["run_id"]))
                connection.execute("INSERT INTO jobs(id,run_id,stage,status) VALUES (?,?,?,?)", (uuid.uuid4().hex, job["run_id"], next_stage, "PENDING"))
                self._event(connection, job["run_id"], "STAGE_READY", next_stage)

    def _parse(self, stage: str, raw: str) -> tuple[dict | None, str | None]:
        try: value = json.loads(raw)
        except json.JSONDecodeError: return None, "invalid JSON worker output"
        if not isinstance(value, dict) or value.get("stage") != stage or "evidence" not in value:
            return None, "artifact contract invalid"
        return value, None

    def _block(self, connection: sqlite3.Connection, run_id: str, reason: str) -> None:
        connection.execute("UPDATE runs SET status='BLOCKED', updated_at=? WHERE id=?", (now(), run_id))
        connection.execute("INSERT OR IGNORE INTO notifications(run_id,kind) VALUES (?,?)", (run_id, f"BLOCKED:{reason}"))
        self._event(connection, run_id, "RUN_BLOCKED", reason)

    def _event(self, connection: sqlite3.Connection, run_id: str, kind: str, detail: str) -> None:
        event_id = uuid.uuid4().hex
        connection.execute("INSERT INTO events VALUES (?,?,?,?,?)", (event_id, run_id, kind, detail, now()))
        connection.execute("INSERT OR IGNORE INTO notifications(run_id,kind) VALUES (?,?)", (run_id, f"EVENT:{event_id}"))

    def pending_notifications(self) -> list[sqlite3.Row]:
        with self.db() as connection:
            return connection.execute("SELECT * FROM notifications WHERE sent_at IS NULL ORDER BY rowid").fetchall()

    def mark_notified(self, run_id: str, kind: str) -> None:
        with self.db() as connection:
            connection.execute("UPDATE notifications SET sent_at=? WHERE run_id=? AND kind=?", (now(), run_id, kind))
