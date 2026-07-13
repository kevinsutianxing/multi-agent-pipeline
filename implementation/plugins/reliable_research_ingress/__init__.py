"""Hermes gateway boundary for the durable research pipeline."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from typing import Any

TRIGGER = re.compile(r"^\s*启动多智能体研究\s*[：:]?\s*(.+?)\s*$", re.S)


def setting(name: str, default: str) -> str:
    return os.environ.get(name, default)


def send_ack(target: str, message: str) -> None:
    hermes_python = setting("HERMES_PYTHON", "/home/ubuntu/.hermes/hermes-agent/venv/bin/python")
    profile = setting("PIPELINE_HERMES_NOTIFY_PROFILE", "hermeskevin")
    subprocess.run(
        [
            hermes_python,
            "-m",
            "hermes_cli.main",
            "--profile",
            profile,
            "send",
            "--to",
            target,
            "--quiet",
            message,
        ],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def intercept(*, event: Any, **_kwargs: Any) -> dict[str, str] | None:
    source = event.source
    platform = getattr(source.platform, "value", str(source.platform))
    if platform != "feishu":
        return None
    match = TRIGGER.match(event.text or "")
    if not match:
        return None
    question = match.group(1).strip()
    target = f"feishu:{source.chat_id}"
    message_id = str(getattr(event, "message_id", ""))
    request_key = hashlib.sha256(f"{target}\0{message_id}\0{question}".encode()).hexdigest()

    host = setting("PIPELINE_REMOTE_HOST", "sz81")
    root = setting("PIPELINE_REMOTE_ROOT", "/home/ubuntu/multi-agent-pipeline/implementation")
    db = setting("PIPELINE_REMOTE_DB", f"{root}/state/pipeline.db")
    control = f"{root}/scripts/reliable_ctl.py"
    remote_command = " ".join(
        [
            "python3",
            shlex.quote(control),
            "--db",
            shlex.quote(db),
            "create",
            "--request-key",
            shlex.quote(request_key),
            "--question-stdin",
            "--requester",
            "hermeskevin",
            "--notify-target",
            shlex.quote(target),
        ]
    )
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", host, remote_command],
            input=question,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
    except Exception as error:
        send_ack(target, f"可靠研究管道创建失败：{error}")
        return {"action": "skip", "reason": "pipeline create exception"}
    if result.returncode != 0:
        detail = result.stderr.strip()[-500:] or f"exit={result.returncode}"
        send_ack(target, f"可靠研究管道创建失败：{detail}")
        return {"action": "skip", "reason": "pipeline create failed"}
    try:
        run_id = json.loads(result.stdout)["run_id"]
    except (json.JSONDecodeError, KeyError, TypeError):
        send_ack(target, "可靠研究管道返回了无效的创建响应；普通 Hermes 工作流已跳过以避免重复执行。")
        return {"action": "skip", "reason": "invalid pipeline response"}
    send_ack(target, f"可靠研究任务已创建：`{run_id}`。后续阶段由统一管道执行并通知。")
    return {"action": "skip", "reason": f"reliable pipeline run {run_id}"}


def register(ctx: Any) -> None:
    ctx.register_hook("pre_gateway_dispatch", intercept)
