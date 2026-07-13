#!/usr/bin/env python3
"""Durable single-path research pipeline.

The controller owns run state. Workers only claim leased jobs and submit raw
outputs. Every model response is preserved before deterministic normalization
and contract validation.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

STAGES = ("QUALIFY", "ACQUIRE", "VALIDATE", "ANALYZE", "REVIEW", "DELIVER")
TERMINAL = {"DONE", "BLOCKED", "FAILED"}

CONTRACTS: dict[str, dict[str, type]] = {
    "QUALIFY": {
        "qualified": bool,
        "research_question": str,
        "scope": list,
        "risks": list,
        "evidence": list,
    },
    "ACQUIRE": {
        "datasets": list,
        "limitations": list,
        "evidence": list,
    },
    "VALIDATE": {
        "overall_pass": bool,
        "checks": list,
        "limitations": list,
        "evidence": list,
    },
    "ANALYZE": {
        "claims": list,
        "methodology": str,
        "limitations": list,
        "evidence": list,
    },
    "REVIEW": {
        "passed": bool,
        "findings": list,
        "evidence": list,
    },
    "DELIVER": {
        "executive_summary": str,
        "report_markdown": str,
        "evidence": list,
    },
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def future_utc(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


class ReliablePipeline:
    def __init__(
        self,
        db_path: Path,
        *,
        max_attempts: int = 3,
        runs_dir: Path | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.max_attempts = max_attempts
        self.runs_dir = Path(runs_dir) if runs_dir else self.db_path.parent / "runs"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def db(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.db() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    request_key TEXT UNIQUE NOT NULL,
                    question TEXT NOT NULL,
                    requester TEXT NOT NULL DEFAULT 'manual',
                    notify_target TEXT,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    lease_until TEXT,
                    worker_id TEXT,
                    error TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE(run_id, stage)
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    worker_id TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    exit_code INTEGER,
                    raw_output TEXT,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    run_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    raw_output TEXT NOT NULL,
                    normalized TEXT,
                    valid INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, stage)
                );
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    run_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    target TEXT,
                    payload TEXT,
                    sent_at TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    PRIMARY KEY(run_id, kind)
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_ready ON jobs(status, lease_until);
                CREATE INDEX IF NOT EXISTS idx_notifications_pending ON notifications(sent_at);
                """
            )
            self._migrate_legacy_columns(connection)

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}

    def _migrate_legacy_columns(self, connection: sqlite3.Connection) -> None:
        migrations = {
            "runs": {
                "requester": "TEXT NOT NULL DEFAULT 'manual'",
                "notify_target": "TEXT",
                "last_error": "TEXT",
            },
            "jobs": {
                "worker_id": "TEXT",
                "created_at": "TEXT",
                "updated_at": "TEXT",
            },
            "attempts": {"worker_id": "TEXT"},
            "notifications": {
                "target": "TEXT",
                "payload": "TEXT",
                "attempts": "INTEGER NOT NULL DEFAULT 0",
                "last_error": "TEXT",
            },
        }
        for table, columns in migrations.items():
            existing = self._columns(connection, table)
            for name, declaration in columns.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
        now = utc_now()
        connection.execute("UPDATE jobs SET created_at=COALESCE(created_at, ?), updated_at=COALESCE(updated_at, ?)", (now, now))
        connection.execute(
            """UPDATE jobs SET status='PENDING', worker_id=NULL, error='migrated abandoned RUNNING job', updated_at=?
            WHERE status='RUNNING' AND lease_until IS NULL""",
            (now,),
        )
        connection.execute(
            """UPDATE notifications SET sent_at=COALESCE(sent_at, ?), last_error=COALESCE(last_error, 'legacy notification had no target')
            WHERE target IS NULL OR target=''""",
            (now,),
        )

    def create(
        self,
        request_key: str,
        question: str,
        *,
        requester: str = "manual",
        notify_target: str | None = None,
    ) -> str:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")
        with self.db() as connection:
            existing = connection.execute("SELECT id FROM runs WHERE request_key=?", (request_key,)).fetchone()
            if existing:
                return str(existing["id"])
            run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:10]}"
            now = utc_now()
            connection.execute(
                """INSERT INTO runs
                (id,request_key,question,requester,notify_target,status,stage,created_at,updated_at,last_error)
                VALUES (?,?,?,?,?,'ACTIVE',?,?,?,NULL)""",
                (run_id, request_key, normalized_question, requester, notify_target, STAGES[0], now, now),
            )
            self._insert_job(connection, run_id, STAGES[0])
            self._event(connection, run_id, "RUN_CREATED", STAGES[0])
        self._persist_run(run_id)
        return run_id

    def _insert_job(self, connection: sqlite3.Connection, run_id: str, stage: str) -> None:
        now = utc_now()
        connection.execute(
            """INSERT OR IGNORE INTO jobs
            (id,run_id,stage,status,attempts,lease_until,worker_id,error,created_at,updated_at)
            VALUES (?, ?, ?, 'PENDING', 0, NULL, NULL, NULL, ?, ?)""",
            (uuid.uuid4().hex, run_id, stage, now, now),
        )

    def claim(self, worker_id: str, *, lease_seconds: int = 1200) -> dict[str, Any] | None:
        connection = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._recover_expired_locked(connection)
            job = connection.execute(
                """SELECT jobs.* FROM jobs
                JOIN runs ON runs.id=jobs.run_id
                WHERE jobs.status='PENDING' AND jobs.attempts < ? AND runs.status='ACTIVE'
                ORDER BY jobs.rowid LIMIT 1""",
                (self.max_attempts,),
            ).fetchone()
            if not job:
                connection.execute("COMMIT")
                return None
            now = utc_now()
            lease_until = future_utc(lease_seconds)
            updated = connection.execute(
                """UPDATE jobs SET status='RUNNING', attempts=attempts+1,
                lease_until=?, worker_id=?, error=NULL, updated_at=?
                WHERE id=? AND status='PENDING'""",
                (lease_until, worker_id, now, job["id"]),
            ).rowcount
            if updated != 1:
                connection.execute("ROLLBACK")
                return None
            attempt_id = uuid.uuid4().hex
            connection.execute(
                "INSERT INTO attempts(id,job_id,worker_id,started_at) VALUES (?,?,?,?)",
                (attempt_id, job["id"], worker_id, now),
            )
            self._event(connection, job["run_id"], "JOB_STARTED", f"{job['stage']} by {worker_id}")
            claimed = connection.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone()
            context = self._job_context_locked(connection, str(job["run_id"]), str(job["stage"]))
            connection.execute("COMMIT")
            result = dict(claimed)
            result["attempt_id"] = attempt_id
            result["context"] = context
            return result
        except Exception:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    def _recover_expired_locked(self, connection: sqlite3.Connection) -> None:
        now_dt = datetime.now(UTC)
        expired = connection.execute("SELECT * FROM jobs WHERE status='RUNNING' AND lease_until IS NOT NULL").fetchall()
        for job in expired:
            lease = parse_utc(job["lease_until"])
            if lease is None or lease > now_dt:
                continue
            if int(job["attempts"]) >= self.max_attempts:
                connection.execute(
                    "UPDATE jobs SET status='FAILED', worker_id=NULL, lease_until=NULL, error=?, updated_at=? WHERE id=?",
                    ("worker lease expired and retry budget exhausted", utc_now(), job["id"]),
                )
                self._block_locked(connection, str(job["run_id"]), "worker lease expired and retry budget exhausted")
            else:
                connection.execute(
                    "UPDATE jobs SET status='PENDING', worker_id=NULL, lease_until=NULL, error=?, updated_at=? WHERE id=?",
                    ("worker lease expired; requeued", utc_now(), job["id"]),
                )
                self._event(connection, job["run_id"], "JOB_RECOVERED", str(job["stage"]))

    def heartbeat(self, job_id: str, worker_id: str, *, lease_seconds: int = 1200) -> bool:
        with self.db() as connection:
            updated = connection.execute(
                """UPDATE jobs SET lease_until=?, updated_at=?
                WHERE id=? AND status='RUNNING' AND worker_id=?""",
                (future_utc(lease_seconds), utc_now(), job_id, worker_id),
            ).rowcount
            return updated == 1

    def finish(self, job_id: str, worker_id: str, raw_output: str, *, exit_code: int = 0) -> dict[str, Any]:
        with self.db() as connection:
            job = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job:
                return {"accepted": False, "reason": "unknown_job"}
            if job["status"] != "RUNNING" or job["worker_id"] != worker_id:
                return {"accepted": False, "reason": "stale_worker"}
            attempt = connection.execute(
                """SELECT id FROM attempts
                WHERE job_id=? AND worker_id=? AND finished_at IS NULL
                ORDER BY rowid DESC LIMIT 1""",
                (job_id, worker_id),
            ).fetchone()
            normalized: dict[str, Any] | None = None
            error: str | None = None
            if exit_code != 0:
                error = f"adapter exited with code {exit_code}"
            else:
                normalized, error = self.normalize_and_validate(str(job["stage"]), raw_output)
            now = utc_now()
            if attempt:
                connection.execute(
                    "UPDATE attempts SET finished_at=?,exit_code=?,raw_output=?,error=? WHERE id=?",
                    (now, exit_code, raw_output, error, attempt["id"]),
                )
            connection.execute(
                """INSERT OR REPLACE INTO artifacts
                (run_id,stage,raw_output,normalized,valid,created_at)
                VALUES (?,?,?,?,?,?)""",
                (
                    job["run_id"],
                    job["stage"],
                    raw_output,
                    json.dumps(normalized, ensure_ascii=False) if normalized is not None else None,
                    int(error is None),
                    now,
                ),
            )
            if error:
                self._handle_failure_locked(connection, job, error)
                result = {"accepted": True, "status": "retry_or_blocked", "error": error}
            else:
                result = self._handle_success_locked(connection, job, normalized or {})
        self._persist_run(str(job["run_id"]))
        return result

    def _handle_failure_locked(self, connection: sqlite3.Connection, job: sqlite3.Row, error: str) -> None:
        attempts = int(job["attempts"])
        if attempts < self.max_attempts:
            connection.execute(
                """UPDATE jobs SET status='PENDING',worker_id=NULL,lease_until=NULL,error=?,updated_at=?
                WHERE id=?""",
                (error, utc_now(), job["id"]),
            )
            self._event(connection, job["run_id"], "JOB_RETRY", f"{job['stage']}: {error}")
        else:
            connection.execute(
                """UPDATE jobs SET status='FAILED',worker_id=NULL,lease_until=NULL,error=?,updated_at=?
                WHERE id=?""",
                (error, utc_now(), job["id"]),
            )
            self._block_locked(connection, str(job["run_id"]), f"{job['stage']}: {error}")

    def _handle_success_locked(
        self,
        connection: sqlite3.Connection,
        job: sqlite3.Row,
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        connection.execute(
            """UPDATE jobs SET status='SUCCEEDED',worker_id=NULL,lease_until=NULL,error=NULL,updated_at=?
            WHERE id=?""",
            (utc_now(), job["id"]),
        )
        self._event(connection, job["run_id"], "JOB_SUCCEEDED", str(job["stage"]))
        blocked_reason = self._gate_failure(str(job["stage"]), artifact)
        if blocked_reason:
            self._block_locked(connection, str(job["run_id"]), blocked_reason)
            return {"accepted": True, "status": "BLOCKED", "reason": blocked_reason}
        index = STAGES.index(str(job["stage"]))
        if index == len(STAGES) - 1:
            connection.execute(
                "UPDATE runs SET status='DONE',updated_at=?,last_error=NULL WHERE id=?",
                (utc_now(), job["run_id"]),
            )
            self._event(connection, job["run_id"], "RUN_DONE", str(job["stage"]))
            self._notify(connection, str(job["run_id"]), "RUN_DONE", "研究任务已完成，报告已生成。")
            return {"accepted": True, "status": "DONE"}
        next_stage = STAGES[index + 1]
        connection.execute(
            "UPDATE runs SET stage=?,updated_at=?,last_error=NULL WHERE id=?",
            (next_stage, utc_now(), job["run_id"]),
        )
        self._insert_job(connection, str(job["run_id"]), next_stage)
        self._event(connection, job["run_id"], "STAGE_READY", next_stage)
        self._notify(connection, str(job["run_id"]), f"STAGE_READY:{next_stage}", f"研究任务进入阶段：{next_stage}")
        return {"accepted": True, "status": "ACTIVE", "next_stage": next_stage}

    @staticmethod
    def _gate_failure(stage: str, artifact: dict[str, Any]) -> str | None:
        if stage == "QUALIFY" and artifact.get("qualified") is not True:
            return "qualification rejected or requires human clarification"
        if stage == "VALIDATE" and artifact.get("overall_pass") is not True:
            return "data validation failed"
        if stage == "REVIEW" and artifact.get("passed") is not True:
            return "independent review found unresolved critical issues"
        return None

    def _block_locked(self, connection: sqlite3.Connection, run_id: str, reason: str) -> None:
        connection.execute(
            "UPDATE runs SET status='BLOCKED',updated_at=?,last_error=? WHERE id=?",
            (utc_now(), reason, run_id),
        )
        self._event(connection, run_id, "RUN_BLOCKED", reason)
        self._notify(connection, run_id, "RUN_BLOCKED", f"研究任务已阻断：{reason}")

    def retry(self, run_id: str) -> dict[str, Any]:
        with self.db() as connection:
            run = connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not run:
                raise ValueError(f"unknown run: {run_id}")
            if run["status"] not in {"BLOCKED", "FAILED"}:
                return self.status(run_id)
            job = connection.execute(
                "SELECT * FROM jobs WHERE run_id=? AND stage=?",
                (run_id, run["stage"]),
            ).fetchone()
            if job:
                connection.execute(
                    """UPDATE jobs SET status='PENDING',attempts=0,lease_until=NULL,worker_id=NULL,error=NULL,updated_at=?
                    WHERE id=?""",
                    (utc_now(), job["id"]),
                )
            else:
                self._insert_job(connection, run_id, str(run["stage"]))
            connection.execute(
                "UPDATE runs SET status='ACTIVE',last_error=NULL,updated_at=? WHERE id=?",
                (utc_now(), run_id),
            )
            self._event(connection, run_id, "RUN_RETRIED", str(run["stage"]))
        self._persist_run(run_id)
        return self.status(run_id)

    def _job_context_locked(self, connection: sqlite3.Connection, run_id: str, stage: str) -> dict[str, Any]:
        run = connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        artifacts: dict[str, Any] = {}
        for row in connection.execute(
            "SELECT stage,normalized FROM artifacts WHERE run_id=? AND valid=1 ORDER BY rowid",
            (run_id,),
        ):
            if row["normalized"]:
                try:
                    artifacts[str(row["stage"])] = json.loads(row["normalized"])
                except json.JSONDecodeError:
                    continue
        return {
            "run_id": run_id,
            "stage": stage,
            "question": str(run["question"]),
            "requester": str(run["requester"]),
            "prior_artifacts": artifacts,
        }

    def context(self, run_id: str) -> dict[str, Any]:
        with self.db() as connection:
            run = connection.execute("SELECT stage FROM runs WHERE id=?", (run_id,)).fetchone()
            if not run:
                raise ValueError(f"unknown run: {run_id}")
            return self._job_context_locked(connection, run_id, str(run["stage"]))

    def status(self, run_id: str) -> dict[str, Any]:
        with self.db() as connection:
            run = connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not run:
                raise ValueError(f"unknown run: {run_id}")
            jobs = [dict(row) for row in connection.execute("SELECT * FROM jobs WHERE run_id=? ORDER BY rowid", (run_id,))]
            artifacts = [
                {
                    **dict(row),
                    "normalized": json.loads(row["normalized"]) if row["normalized"] else None,
                }
                for row in connection.execute(
                    "SELECT stage,valid,normalized,created_at FROM artifacts WHERE run_id=? ORDER BY rowid",
                    (run_id,),
                )
            ]
            return {"run": dict(run), "jobs": jobs, "artifacts": artifacts}

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.db() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM runs ORDER BY rowid DESC LIMIT ?", (limit,))]

    def health(self) -> dict[str, Any]:
        with self.db() as connection:
            statuses = {row["status"]: row["count"] for row in connection.execute("SELECT status,COUNT(*) AS count FROM runs GROUP BY status")}
            pending_jobs = connection.execute("SELECT COUNT(*) FROM jobs WHERE status='PENDING'").fetchone()[0]
            running_jobs = connection.execute("SELECT COUNT(*) FROM jobs WHERE status='RUNNING'").fetchone()[0]
            pending_notifications = connection.execute("SELECT COUNT(*) FROM notifications WHERE sent_at IS NULL").fetchone()[0]
        return {
            "ok": True,
            "db": str(self.db_path),
            "runs_dir": str(self.runs_dir),
            "run_statuses": statuses,
            "pending_jobs": pending_jobs,
            "running_jobs": running_jobs,
            "pending_notifications": pending_notifications,
        }

    def _event(self, connection: sqlite3.Connection, run_id: str, kind: str, detail: str) -> None:
        connection.execute(
            "INSERT INTO events(id,run_id,kind,detail,created_at) VALUES (?,?,?,?,?)",
            (uuid.uuid4().hex, run_id, kind, detail, utc_now()),
        )

    def _notify(self, connection: sqlite3.Connection, run_id: str, kind: str, message: str) -> None:
        run = connection.execute("SELECT notify_target FROM runs WHERE id=?", (run_id,)).fetchone()
        target = str(run["notify_target"] or "") if run else ""
        if not target:
            return
        payload = json.dumps(
            {"run_id": run_id, "kind": kind, "target": target, "message": message},
            ensure_ascii=False,
        )
        connection.execute(
            """INSERT OR IGNORE INTO notifications
            (run_id,kind,target,payload,sent_at,attempts,last_error)
            VALUES (?,?,?,?,NULL,0,NULL)""",
            (run_id, kind, target, payload),
        )

    def pending_notifications(self, limit: int = 100) -> list[sqlite3.Row]:
        with self.db() as connection:
            return connection.execute(
                "SELECT * FROM notifications WHERE sent_at IS NULL ORDER BY rowid LIMIT ?",
                (limit,),
            ).fetchall()

    def mark_notification(self, run_id: str, kind: str, *, error: str | None = None) -> None:
        with self.db() as connection:
            if error is None:
                connection.execute(
                    "UPDATE notifications SET sent_at=?,attempts=attempts+1,last_error=NULL WHERE run_id=? AND kind=?",
                    (utc_now(), run_id, kind),
                )
            else:
                connection.execute(
                    "UPDATE notifications SET attempts=attempts+1,last_error=? WHERE run_id=? AND kind=?",
                    (error[:1000], run_id, kind),
                )

    @classmethod
    def normalize_and_validate(cls, stage: str, raw_output: str) -> tuple[dict[str, Any] | None, str | None]:
        candidates = cls._extract_json_objects(raw_output)
        if not candidates:
            return None, "no JSON object found in adapter output"
        selected: dict[str, Any] | None = None
        for candidate in candidates:
            value = candidate.get("result") if isinstance(candidate.get("result"), dict) else candidate
            if isinstance(value, dict) and value.get("stage") == stage:
                selected = value
                break
        if selected is None:
            selected = candidates[0]
            if isinstance(selected.get("result"), dict):
                selected = selected["result"]
            return selected, f"artifact stage mismatch: expected {stage}"
        contract = CONTRACTS.get(stage)
        if not contract:
            return selected, f"unknown stage contract: {stage}"
        for key, expected_type in contract.items():
            if key not in selected:
                return selected, f"artifact missing required field: {key}"
            if not isinstance(selected[key], expected_type):
                return selected, f"artifact field {key} must be {expected_type.__name__}"
        if stage == "DELIVER" and not selected["report_markdown"].strip():
            return selected, "report_markdown must not be empty"
        return selected, None

    @classmethod
    def _extract_json_objects(cls, raw_output: str) -> list[dict[str, Any]]:
        text = (raw_output or "").strip()
        if not text:
            return []
        decoder = json.JSONDecoder()
        objects: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(value: Any) -> None:
            if not isinstance(value, dict):
                return
            fingerprint = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
            if fingerprint in seen:
                return
            seen.add(fingerprint)
            objects.append(value)
            for key in ("result", "content", "message"):
                nested = value.get(key)
                if isinstance(nested, dict):
                    add(nested)
                elif isinstance(nested, str):
                    for item in cls._extract_json_objects(nested):
                        add(item)

        try:
            add(json.loads(text))
        except json.JSONDecodeError:
            pass
        for fenced in re.findall(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.I | re.S):
            try:
                add(json.loads(fenced))
            except json.JSONDecodeError:
                pass
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                value, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            add(value)
        return objects

    def _persist_run(self, run_id: str) -> None:
        try:
            status = self.status(run_id)
        except ValueError:
            return
        run_dir = self.runs_dir / run_id
        _write_text_atomic(run_dir / "status.json", json.dumps(status, ensure_ascii=False, indent=2) + "\n")
        with self.db() as connection:
            rows = connection.execute(
                "SELECT stage,raw_output,normalized,valid FROM artifacts WHERE run_id=? ORDER BY rowid",
                (run_id,),
            ).fetchall()
        for row in rows:
            stage_name = str(row["stage"]).lower()
            _write_text_atomic(run_dir / "raw" / f"{stage_name}.txt", str(row["raw_output"]))
            if row["normalized"]:
                parsed = json.loads(row["normalized"])
                _write_text_atomic(run_dir / "artifacts" / f"{stage_name}.json", json.dumps(parsed, ensure_ascii=False, indent=2) + "\n")
                if row["stage"] == "DELIVER" and row["valid"]:
                    _write_text_atomic(run_dir / "report.md", parsed["report_markdown"].rstrip() + "\n")
