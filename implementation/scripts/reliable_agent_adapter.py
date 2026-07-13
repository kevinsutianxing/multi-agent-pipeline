#!/usr/bin/env python3
"""Stateless adapter from a leased pipeline job to the configured agents.

Input is one JSON object on stdin. Output is the agent's raw stdout; the
controller persists and normalizes it deterministically.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
from typing import Any

from reliable_pipeline import CONTRACTS

ROLE_BY_STAGE = {
    "QUALIFY": "codex",
    "ACQUIRE": "hermescold",
    "VALIDATE": "deterministic",
    "ANALYZE": "hermescold",
    "REVIEW": "claude",
    "DELIVER": "codex",
}

DEFAULT_COMMANDS = {
    "codex": "ssh hk43 codex exec --ephemeral --sandbox read-only -",
    "claude": "claude --safe-mode --print --output-format text --permission-mode plan",
    "hermescold": "ssh hk43 /home/ubuntu/.local/bin/hermescold-pipeline-worker.py",
}


def command_for(role: str) -> list[str]:
    env_name = f"PIPELINE_{role.upper()}_CMD"
    return shlex.split(os.environ.get(env_name, DEFAULT_COMMANDS[role]))


def compact_json(value: Any, limit: int = 60000) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= limit:
        return text
    return json.dumps(
        {
            "truncated": True,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "original_characters": len(text),
            "preview": text[:limit],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def stage_prompt(context: dict[str, Any]) -> str:
    stage = str(context["stage"])
    required = {key: expected.__name__ for key, expected in CONTRACTS[stage].items()}
    prior = context.get("prior_artifacts") or {}
    stage_guidance = {
        "QUALIFY": (
            "Decide whether the question is sufficiently defined for evidence-based financial research. "
            "Do not invent missing scope. Set qualified=false when a material ambiguity prevents safe work."
        ),
        "ACQUIRE": (
            "Build a source manifest, not a narrative answer. Each dataset should identify dataset_id, "
            "source_name, source_ref or URL, retrieved_at, observations, and validation_status. "
            "Use only sources actually accessed; record unavailable data in limitations."
        ),
        "ANALYZE": (
            "Analyze only the validated acquired evidence. Each claim should include claim_text, evidence_refs, "
            "confidence, and reasoning. Separate facts, calculations, and inferences."
        ),
        "REVIEW": (
            "Adversarially review the analysis against the source manifest and validation artifact. "
            "Set passed=false for unsupported claims, date/unit errors, missing evidence, or material omissions."
        ),
        "DELIVER": (
            "Produce a self-contained Markdown report grounded in the prior artifacts. Include an executive "
            "summary, evidence-backed findings, limitations, and source/evidence references."
        ),
    }.get(stage, "")
    return f"""You are the {ROLE_BY_STAGE[stage]} executor in a durable evidence-gated research pipeline.

Research question:
{context['question']}

Current stage: {stage}
Prior validated artifacts (machine JSON):
{compact_json(prior)}

Stage instructions:
{stage_guidance}

Return one JSON object. Markdown fences or a short preface are tolerated by the controller, but the JSON object is mandatory.
The JSON object MUST include \"stage\": \"{stage}\" and these fields with the stated JSON types:
{json.dumps(required, ensure_ascii=False, indent=2)}

Non-negotiable rules:
- Never fabricate a source, date, price, filing, dataset, calculation, or tool result.
- Preserve uncertainty and limitations explicitly.
- Every factual claim must trace to an evidence item or prior artifact.
- Do not claim completion when required evidence is unavailable.
"""


def deterministic_validate(context: dict[str, Any]) -> dict[str, Any]:
    acquired = (context.get("prior_artifacts") or {}).get("ACQUIRE") or {}
    datasets = acquired.get("datasets") if isinstance(acquired, dict) else None
    checks: list[dict[str, Any]] = []
    limitations = list(acquired.get("limitations") or []) if isinstance(acquired, dict) else []
    overall_pass = isinstance(datasets, list) and bool(datasets)
    if not isinstance(datasets, list):
        datasets = []
    for index, dataset in enumerate(datasets):
        valid = isinstance(dataset, dict)
        required_identity = bool(dataset.get("source_name")) and bool(dataset.get("source_ref") or dataset.get("url")) if valid else False
        required_time = bool(dataset.get("retrieved_at")) if valid else False
        has_observations = bool(dataset.get("observations") or dataset.get("data") or dataset.get("facts")) if valid else False
        status_ok = dataset.get("validation_status") in {"passed", "passed_with_limitations", "unverified"} if valid else False
        passed = valid and required_identity and required_time and has_observations and status_ok
        checks.append(
            {
                "dataset_index": index,
                "passed": passed,
                "source_identity": required_identity,
                "retrieved_at": required_time,
                "observations_present": has_observations,
                "declared_status": dataset.get("validation_status") if valid else None,
            }
        )
        overall_pass = overall_pass and passed and dataset.get("validation_status") != "unverified"
    if not datasets:
        limitations.append("No datasets were acquired.")
    return {
        "stage": "VALIDATE",
        "overall_pass": bool(overall_pass),
        "checks": checks,
        "limitations": limitations,
        "evidence": [
            {
                "kind": "deterministic_validation",
                "dataset_count": len(datasets),
                "rule": "identity + retrieval time + observations + passed validation status",
            }
        ],
    }


def run_agent(role: str, prompt: str, timeout: int) -> subprocess.CompletedProcess[str]:
    command = command_for(role)
    if role == "claude":
        return subprocess.run(command + [prompt], text=True, capture_output=True, timeout=timeout, check=False)
    if role == "hermescold":
        return subprocess.run(
            command,
            input=json.dumps({"prompt": prompt}, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    return subprocess.run(command, input=prompt, text=True, capture_output=True, timeout=timeout, check=False)


def main() -> int:
    request = json.loads(sys.stdin.read())
    context = request.get("context") or {}
    stage = str(request.get("stage") or context.get("stage") or "")
    if stage not in ROLE_BY_STAGE:
        raise SystemExit(f"unsupported stage: {stage}")
    context["stage"] = stage
    if stage == "VALIDATE":
        print(json.dumps(deterministic_validate(context), ensure_ascii=False))
        return 0
    prompt = stage_prompt(context)
    timeout = int(os.environ.get("PIPELINE_AGENT_TIMEOUT_SECONDS", "900"))
    result = run_agent(ROLE_BY_STAGE[stage], prompt, timeout)
    sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
