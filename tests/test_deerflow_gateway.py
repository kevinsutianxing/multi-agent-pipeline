from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from adapters.deerflow_gateway import (
    DeerFlowGateway,
    DeerFlowURLs,
    iter_sse,
)


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self.body

    def __iter__(self):
        return iter(self.body.splitlines(keepends=True))


def make_gateway() -> DeerFlowGateway:
    return DeerFlowGateway(
        DeerFlowURLs(
            gateway="http://deerflow.test",
            langgraph="http://deerflow.test/api/langgraph",
        )
    )


def test_build_run_payload_routes_to_custom_agent() -> None:
    gateway = make_gateway()
    payload = gateway.build_run_payload(
        thread_id="thread-1",
        assistant_id="finance-evidence-agent",
        message="collect evidence",
        mode="ultra",
        recursion_limit=500,
        max_concurrent_subagents=2,
    )
    assert payload["assistant_id"] == "finance-evidence-agent"
    assert payload["context"] == {
        "thinking_enabled": True,
        "is_plan_mode": True,
        "subagent_enabled": True,
        "thread_id": "thread-1",
        "max_concurrent_subagents": 2,
    }
    assert payload["config"]["recursion_limit"] == 500


def test_iter_sse_parses_multiline_events() -> None:
    raw = (
        b"event: metadata\n"
        b"data: {\"run_id\":\"run-1\"}\n\n"
        b"event: messages-tuple\n"
        b"data: {\"type\":\"ai\",\"content\":\"hello\",\"id\":\"m1\"}\n\n"
    )
    events = list(iter_sse(FakeResponse(raw)))
    assert events[0]["event"] == "metadata"
    assert events[0]["data"]["run_id"] == "run-1"
    assert events[1]["data"]["content"] == "hello"


def test_run_and_record_preserves_request_and_events(tmp_path: Path) -> None:
    gateway = make_gateway()
    sse = (
        b"event: metadata\n"
        b"data: {\"run_id\":\"run-1\",\"thread_id\":\"thread-1\"}\n\n"
        b"event: messages-tuple\n"
        b"data: {\"type\":\"ai\",\"content\":\"draft\",\"id\":\"m1\"}\n\n"
        b"event: values\n"
        b"data: {\"messages\":[{\"type\":\"ai\",\"content\":\"final answer\"}],\"artifacts\":[{\"path\":\"report.md\"}]}\n\n"
        b"event: end\n"
        b"data: {}\n\n"
    )
    responses = [
        FakeResponse(b'{"status":"ok"}'),
        FakeResponse(b'{"thread_id":"thread-1"}'),
        FakeResponse(sse),
    ]
    with patch("adapters.deerflow_gateway.urlopen", side_effect=responses):
        result = gateway.run_and_record(
            run_dir=tmp_path,
            task_id="task-1",
            assistant_id="industry-research-agent",
            message="research the industry",
            mode="pro",
        )

    assert result["status"] == "COMPLETED"
    assert result["run_id"] == "run-1"
    assert result["thread_id"] == "thread-1"
    assert result["final_text"] == "final answer"
    assert result["event_count"] == 4

    record_dir = tmp_path / "deerflow" / "task-1"
    request = json.loads((record_dir / "request.json").read_text(encoding="utf-8"))
    persisted = json.loads((record_dir / "result.json").read_text(encoding="utf-8"))
    event_lines = (record_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()

    assert request["payload"]["assistant_id"] == "industry-research-agent"
    assert persisted["request_sha256"]
    assert persisted["events_sha256"]
    assert len(event_lines) == 4
