"""Ingress boundary: create v2 work, then prevent normal agent dispatch."""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess


TRIGGER = re.compile(r"^\s*启动多智能体研究\s*[：:]?\s*(.+?)\s*$", re.S)
CONTROL = "/home/ubuntu/multi-agent-pipeline/scripts/reliable_ctl.py"
HERMES = "/home/ubuntu/.hermes/hermes-agent/venv/bin/python"


def _send(chat_id: str, message: str) -> None:
    subprocess.run([HERMES, "-m", "hermes_cli.main", "--profile", "hermeskevin", "send", "--to", f"feishu:{chat_id}", "--quiet", message], capture_output=True, text=True, timeout=30, check=False)


def intercept(*, event, **_kwargs):
    source = event.source
    if getattr(source.platform, "value", str(source.platform)) != "feishu":
        return None
    match = TRIGGER.match(event.text or "")
    if not match:
        return None
    question = match.group(1)
    request_key = hashlib.sha256(f"{source.chat_id}\0{getattr(event, 'message_id', '')}\0{question}".encode()).hexdigest()
    command = f"python3 {shlex.quote(CONTROL)} create --request-key {shlex.quote(request_key)} --question {shlex.quote(question)}"
    result = subprocess.run(["ssh", "sz81", command], capture_output=True, text=True, timeout=45, check=False)
    if result.returncode:
        _send(source.chat_id, "可靠研究管道创建失败；未转交给普通 Hermes 工作流。")
        return {"action": "skip", "reason": "v2 create failed"}
    try:
        run_id = json.loads(result.stdout)["run_id"]
    except (json.JSONDecodeError, KeyError):
        _send(source.chat_id, "可靠研究管道创建失败；未转交给普通 Hermes 工作流。")
        return {"action": "skip", "reason": "v2 invalid create response"}
    _send(source.chat_id, f"可靠研究任务已创建：`{run_id}`。普通 Hermes/leaf 工作流已跳过；后续只由 v2 节点通知。")
    return {"action": "skip", "reason": f"reliable v2 run {run_id}"}


def register(ctx):
    ctx.register_hook("pre_gateway_dispatch", intercept)
