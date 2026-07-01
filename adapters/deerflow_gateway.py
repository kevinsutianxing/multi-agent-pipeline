#!/usr/bin/env python3
"""Auditable HTTP adapter for the official ByteDance DeerFlow 2.x Gateway.

This module treats DeerFlow as an agent execution harness, not as a financial
data source. It records the exact request, raw SSE event stream, thread/run IDs,
and final response under the research run directory.

API shape follows the official DeerFlow Gateway / LangGraph-compatible API:
- GET  /health
- GET  /api/agents
- POST /api/agents
- PUT  /api/agents/{name}
- POST /api/langgraph/threads
- POST /api/langgraph/threads/{thread_id}/runs/stream
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODE_CONTEXTS: dict[str, dict[str, bool]] = {
    "flash": {
        "thinking_enabled": False,
        "is_plan_mode": False,
        "subagent_enabled": False,
    },
    "standard": {
        "thinking_enabled": True,
        "is_plan_mode": False,
        "subagent_enabled": False,
    },
    "pro": {
        "thinking_enabled": True,
        "is_plan_mode": True,
        "subagent_enabled": False,
    },
    "ultra": {
        "thinking_enabled": True,
        "is_plan_mode": True,
        "subagent_enabled": True,
    },
}

SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class DeerFlowError(RuntimeError):
    """Base adapter error."""


class DeerFlowHTTPError(DeerFlowError):
    """HTTP response error with status and response body."""

    def __init__(self, status: int, message: str):
        super().__init__(f"DeerFlow HTTP {status}: {message}")
        self.status = status
        self.message = message


@dataclass(frozen=True)
class DeerFlowURLs:
    gateway: str
    langgraph: str

    @classmethod
    def from_env(cls) -> "DeerFlowURLs":
        unified = os.getenv("DEERFLOW_URL", "http://localhost:2026").rstrip("/")
        gateway = os.getenv("DEERFLOW_GATEWAY_URL", unified).rstrip("/")
        langgraph = os.getenv(
            "DEERFLOW_LANGGRAPH_URL", f"{unified}/api/langgraph"
        ).rstrip("/")
        return cls(gateway=gateway, langgraph=langgraph)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def extract_text(content: Any) -> str:
    """Normalize LangChain string or rich block content into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    if content is None:
        return ""
    return str(content)


def iter_sse(response: Iterable[bytes]) -> Iterable[dict[str, Any]]:
    """Parse a byte-line SSE response into event dictionaries."""
    event_name = "message"
    event_id: str | None = None
    data_lines: list[str] = []

    def emit() -> dict[str, Any] | None:
        nonlocal event_name, event_id, data_lines
        if not data_lines and event_name == "message" and event_id is None:
            return None
        raw_data = "\n".join(data_lines)
        try:
            data: Any = json.loads(raw_data) if raw_data else None
        except json.JSONDecodeError:
            data = raw_data
        item = {"event": event_name, "data": data}
        if event_id is not None:
            item["id"] = event_id
        event_name = "message"
        event_id = None
        data_lines = []
        return item

    for raw in response:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line == "":
            item = emit()
            if item is not None:
                yield item
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)
        elif field == "id":
            event_id = value

    item = emit()
    if item is not None:
        yield item


class DeerFlowGateway:
    def __init__(
        self,
        urls: DeerFlowURLs | None = None,
        *,
        timeout_seconds: int = 3600,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.urls = urls or DeerFlowURLs.from_env()
        self.timeout_seconds = timeout_seconds
        self.extra_headers = dict(extra_headers or {})

    def _request(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
        *,
        accept: str = "application/json",
    ):
        body = canonical_json(payload) if payload is not None else None
        headers = {
            "Accept": accept,
            **self.extra_headers,
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            return urlopen(request, timeout=self.timeout_seconds)
        except HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            raise DeerFlowHTTPError(exc.code, response_body) from exc
        except URLError as exc:
            raise DeerFlowError(f"Cannot reach DeerFlow at {url}: {exc}") from exc

    def _json_request(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._request(method, url, payload) as response:
            raw = response.read()
        try:
            value = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise DeerFlowError(f"Invalid JSON response from {url}") from exc
        if not isinstance(value, dict):
            raise DeerFlowError(f"Expected JSON object from {url}")
        return value

    def health(self) -> dict[str, Any]:
        return self._json_request("GET", f"{self.urls.gateway}/health")

    def list_agents(self) -> dict[str, Any]:
        return self._json_request("GET", f"{self.urls.gateway}/api/agents")

    def get_agent(self, name: str) -> dict[str, Any]:
        return self._json_request("GET", f"{self.urls.gateway}/api/agents/{name}")

    def sync_agent(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Create or update a custom agent from an official API request spec."""
        name = str(spec.get("name") or "")
        if not name or not SAFE_NAME_RE.fullmatch(name):
            raise DeerFlowError(f"Invalid custom agent name: {name!r}")
        try:
            self.get_agent(name)
        except DeerFlowHTTPError as exc:
            if exc.status != 404:
                raise
            return self._json_request(
                "POST", f"{self.urls.gateway}/api/agents", spec
            )
        update = {key: value for key, value in spec.items() if key != "name"}
        return self._json_request(
            "PUT", f"{self.urls.gateway}/api/agents/{name}", update
        )

    def create_thread(self) -> str:
        response = self._json_request(
            "POST", f"{self.urls.langgraph}/threads", {}
        )
        thread_id = response.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id:
            raise DeerFlowError("Thread creation response has no thread_id")
        return thread_id

    def build_run_payload(
        self,
        *,
        thread_id: str,
        assistant_id: str,
        message: str,
        mode: str,
        recursion_limit: int,
        max_concurrent_subagents: int = 3,
    ) -> dict[str, Any]:
        if mode not in MODE_CONTEXTS:
            raise DeerFlowError(f"Unsupported DeerFlow mode: {mode}")
        context: dict[str, Any] = {
            **MODE_CONTEXTS[mode],
            "thread_id": thread_id,
        }
        if context["subagent_enabled"]:
            context["max_concurrent_subagents"] = max_concurrent_subagents
        return {
            "assistant_id": assistant_id,
            "input": {
                "messages": [
                    {
                        "type": "human",
                        "content": [{"type": "text", "text": message}],
                    }
                ]
            },
            "stream_mode": ["values", "messages-tuple"],
            "stream_subgraphs": True,
            "config": {"recursion_limit": recursion_limit},
            "context": context,
        }

    def stream_run(
        self,
        *,
        thread_id: str,
        assistant_id: str,
        message: str,
        mode: str = "pro",
        recursion_limit: int = 300,
        max_concurrent_subagents: int = 3,
    ) -> dict[str, Any]:
        payload = self.build_run_payload(
            thread_id=thread_id,
            assistant_id=assistant_id,
            message=message,
            mode=mode,
            recursion_limit=recursion_limit,
            max_concurrent_subagents=max_concurrent_subagents,
        )
        url = f"{self.urls.langgraph}/threads/{thread_id}/runs/stream"
        with self._request(
            "POST", url, payload, accept="text/event-stream"
        ) as response:
            events = list(iter_sse(response))

        run_id: str | None = None
        artifacts: list[Any] = []
        final_text = ""
        chunk_buffers: dict[str, list[str]] = {}
        error_messages: list[str] = []
        ended = False

        for event in events:
            name = event.get("event")
            data = event.get("data")
            if name == "metadata" and isinstance(data, dict):
                candidate = data.get("run_id")
                if isinstance(candidate, str):
                    run_id = candidate
            elif name == "messages-tuple" and isinstance(data, dict):
                if data.get("type") == "ai":
                    chunk = extract_text(data.get("content"))
                    if chunk:
                        message_id = str(data.get("id") or "unknown")
                        chunk_buffers.setdefault(message_id, []).append(chunk)
            elif name == "values" and isinstance(data, dict):
                value_artifacts = data.get("artifacts")
                if isinstance(value_artifacts, list):
                    artifacts = value_artifacts
                messages = data.get("messages")
                if isinstance(messages, list):
                    for message_record in reversed(messages):
                        if isinstance(message_record, dict) and message_record.get(
                            "type"
                        ) == "ai":
                            candidate = extract_text(message_record.get("content"))
                            if candidate:
                                final_text = candidate
                                break
            elif name == "error":
                error_messages.append(extract_text(data))
            elif name == "end":
                ended = True

        if not final_text and chunk_buffers:
            final_key = next(reversed(chunk_buffers))
            final_text = "".join(chunk_buffers[final_key])

        return {
            "status": "COMPLETED" if ended and not error_messages else "FAILED",
            "thread_id": thread_id,
            "run_id": run_id,
            "assistant_id": assistant_id,
            "mode": mode,
            "final_text": final_text,
            "artifacts": artifacts,
            "errors": error_messages,
            "events": events,
            "request": payload,
        }

    def run_and_record(
        self,
        *,
        run_dir: Path,
        task_id: str,
        assistant_id: str,
        message: str,
        mode: str = "pro",
        thread_id: str | None = None,
        recursion_limit: int = 300,
        max_concurrent_subagents: int = 3,
    ) -> dict[str, Any]:
        if not SAFE_NAME_RE.fullmatch(task_id):
            raise DeerFlowError(f"Unsafe task_id: {task_id!r}")
        task_dir = run_dir.resolve() / "deerflow" / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        health = self.health()
        effective_thread_id = thread_id or self.create_thread()
        result = self.stream_run(
            thread_id=effective_thread_id,
            assistant_id=assistant_id,
            message=message,
            mode=mode,
            recursion_limit=recursion_limit,
            max_concurrent_subagents=max_concurrent_subagents,
        )

        request_record = {
            "gateway_url": self.urls.gateway,
            "langgraph_url": self.urls.langgraph,
            "health": health,
            "payload": result["request"],
        }
        request_bytes = canonical_json(request_record)
        (task_dir / "request.json").write_bytes(request_bytes + b"\n")

        event_lines = b"".join(
            canonical_json(event) + b"\n" for event in result["events"]
        )
        (task_dir / "events.jsonl").write_bytes(event_lines)

        persisted = {
            key: value
            for key, value in result.items()
            if key not in {"events", "request"}
        }
        persisted["request_sha256"] = sha256_bytes(request_bytes)
        persisted["events_sha256"] = sha256_bytes(event_lines)
        persisted["event_count"] = len(result["events"])
        persisted["record_dir"] = str(task_dir)
        result_bytes = canonical_json(persisted)
        (task_dir / "result.json").write_bytes(result_bytes + b"\n")
        return persisted


def load_message(args: argparse.Namespace) -> str:
    if args.message is not None:
        return args.message
    return args.message_file.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Call and audit DeerFlow Gateway")
    parser.add_argument("--timeout", type=int, default=3600)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health")
    subparsers.add_parser("agents")

    sync_parser = subparsers.add_parser("sync-agent")
    sync_parser.add_argument("--spec", required=True, type=Path)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--run-dir", required=True, type=Path)
    run_parser.add_argument("--task-id", required=True)
    run_parser.add_argument("--agent", required=True)
    message_group = run_parser.add_mutually_exclusive_group(required=True)
    message_group.add_argument("--message")
    message_group.add_argument("--message-file", type=Path)
    run_parser.add_argument(
        "--mode", choices=tuple(MODE_CONTEXTS), default="pro"
    )
    run_parser.add_argument("--thread-id")
    run_parser.add_argument("--recursion-limit", type=int, default=300)
    run_parser.add_argument("--max-subagents", type=int, default=3)

    args = parser.parse_args()
    gateway = DeerFlowGateway(timeout_seconds=args.timeout)
    try:
        if args.command == "health":
            output = gateway.health()
        elif args.command == "agents":
            output = gateway.list_agents()
        elif args.command == "sync-agent":
            spec = json.loads(args.spec.read_text(encoding="utf-8"))
            if not isinstance(spec, dict):
                raise DeerFlowError("Agent spec must be a JSON object")
            output = gateway.sync_agent(spec)
        else:
            output = gateway.run_and_record(
                run_dir=args.run_dir,
                task_id=args.task_id,
                assistant_id=args.agent,
                message=load_message(args),
                mode=args.mode,
                thread_id=args.thread_id,
                recursion_limit=args.recursion_limit,
                max_concurrent_subagents=args.max_subagents,
            )
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if output.get("status") != "FAILED" else 1
    except (DeerFlowError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
