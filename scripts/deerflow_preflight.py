#!/usr/bin/env python3
"""Deterministic preflight for an official DeerFlow financial-research deployment.

The preflight checks a deployment manifest, local MCP configuration, official
DeerFlow health, and (when management access is enabled) the approved Custom
Agent inventory. It deliberately fails on example placeholders.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from adapters.deerflow_gateway import DeerFlowError, DeerFlowGateway

SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")
IMAGE_DIGEST_RE = re.compile(r"^sha256:[a-fA-F0-9]{64}$")
PLACEHOLDER_MARKERS = (
    "REPLACE_WITH",
    "your_financial_data_mcp_server",
    "example.invalid",
    "CHANGEME",
)
REQUIRED_AGENTS = {
    "finance-evidence-agent",
    "industry-research-agent",
    "quant-analysis-agent",
}
REQUIRED_MCP_SERVERS = {"financial-data"}


@dataclass
class Check:
    name: str
    status: str
    detail: str


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def contains_placeholder(value: Any) -> bool:
    serialized = json.dumps(value, ensure_ascii=False)
    return any(marker in serialized for marker in PLACEHOLDER_MARKERS)


def validate_deployment_manifest(
    manifest: dict[str, Any],
    *,
    config_path: Path | None = None,
    extensions_path: Path | None = None,
) -> list[Check]:
    checks: list[Check] = []

    repository = manifest.get("official_repository")
    checks.append(
        Check(
            "official_repository",
            "PASS" if repository == "bytedance/deer-flow" else "FAIL",
            str(repository),
        )
    )

    ref = str(manifest.get("official_ref") or "")
    ref_ok = (
        len(ref) >= 7
        and ref not in {"main", "master", "latest", "HEAD"}
        and not contains_placeholder(ref)
    )
    checks.append(
        Check(
            "official_ref_pinned",
            "PASS" if ref_ok else "FAIL",
            ref or "missing",
        )
    )

    sandbox_mode = manifest.get("sandbox_mode")
    sandbox_ok = sandbox_mode in {"container", "kubernetes", "e2b"}
    checks.append(
        Check(
            "isolated_sandbox",
            "PASS" if sandbox_ok else "FAIL",
            str(sandbox_mode),
        )
    )

    image_digest = manifest.get("sandbox_image_digest")
    image_required = sandbox_mode in {"container", "kubernetes"}
    image_ok = (
        not image_required
        or (isinstance(image_digest, str) and bool(IMAGE_DIGEST_RE.fullmatch(image_digest)))
    )
    checks.append(
        Check(
            "sandbox_image_pinned",
            "PASS" if image_ok else "FAIL",
            str(image_digest),
        )
    )

    required_boolean_values = {
        "allow_host_bash": False,
        "memory_injection_enabled": False,
        "skill_evolution_enabled": False,
        "tool_search_enabled": True,
        "guardrails_enabled": True,
        "guardrails_fail_closed": True,
    }
    for field, expected in required_boolean_values.items():
        actual = manifest.get(field)
        checks.append(
            Check(
                field,
                "PASS" if actual is expected else "FAIL",
                f"expected {expected}, got {actual}",
            )
        )

    agents = set(manifest.get("expected_agents") or [])
    missing_agents = sorted(REQUIRED_AGENTS - agents)
    checks.append(
        Check(
            "declared_custom_agents",
            "PASS" if not missing_agents else "FAIL",
            "complete" if not missing_agents else f"missing {missing_agents}",
        )
    )

    mcp_servers = set(manifest.get("expected_mcp_servers") or [])
    missing_mcp = sorted(REQUIRED_MCP_SERVERS - mcp_servers)
    checks.append(
        Check(
            "declared_financial_mcp",
            "PASS" if not missing_mcp else "FAIL",
            "complete" if not missing_mcp else f"missing {missing_mcp}",
        )
    )

    synced_at = manifest.get("custom_agents_synced_at")
    checks.append(
        Check(
            "custom_agents_synced",
            "PASS" if isinstance(synced_at, str) and synced_at else "FAIL",
            str(synced_at),
        )
    )

    for name, path, manifest_field in (
        ("config_hash", config_path, "config_sha256"),
        ("extensions_hash", extensions_path, "extensions_config_sha256"),
    ):
        expected_hash = manifest.get(manifest_field)
        if path is None:
            checks.append(Check(name, "SKIP", "path not supplied"))
            continue
        if not path.is_file():
            checks.append(Check(name, "FAIL", f"missing file: {path}"))
            continue
        if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
            checks.append(Check(name, "FAIL", f"invalid declared hash: {expected_hash}"))
            continue
        actual_hash = sha256_file(path)
        checks.append(
            Check(
                name,
                "PASS" if actual_hash.lower() == expected_hash.lower() else "FAIL",
                f"actual {actual_hash}",
            )
        )

    return checks


def extract_mcp_servers(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("mcpServers")
    if not isinstance(value, dict):
        value = config.get("mcp_servers")
    return value if isinstance(value, dict) else {}


def validate_extensions_config(config: dict[str, Any]) -> list[Check]:
    checks: list[Check] = []
    servers = extract_mcp_servers(config)
    server = servers.get("financial-data")
    if not isinstance(server, dict):
        return [Check("financial_data_mcp_config", "FAIL", "financial-data server missing")]

    checks.append(
        Check(
            "financial_data_mcp_enabled",
            "PASS" if server.get("enabled") is True else "FAIL",
            f"enabled={server.get('enabled')}",
        )
    )
    checks.append(
        Check(
            "financial_data_mcp_placeholder_free",
            "FAIL" if contains_placeholder(server) else "PASS",
            "placeholder found" if contains_placeholder(server) else "no placeholder markers",
        )
    )

    transport_type = str(server.get("type") or "stdio").lower()
    if transport_type == "stdio":
        executable = server.get("command")
        args = server.get("args")
        valid_transport = isinstance(executable, str) and executable and isinstance(args, list)
    else:
        valid_transport = transport_type in {"http", "sse"} and isinstance(server.get("url"), str)
    checks.append(
        Check(
            "financial_data_mcp_transport",
            "PASS" if valid_transport else "FAIL",
            transport_type,
        )
    )
    return checks


def validate_live_deerflow(
    gateway: DeerFlowGateway,
    expected_agents: set[str],
    *,
    check_agent_inventory: bool,
) -> list[Check]:
    checks: list[Check] = []
    try:
        health = gateway.health()
        checks.append(Check("deerflow_health", "PASS", json.dumps(health, ensure_ascii=False)))
    except DeerFlowError as exc:
        return [Check("deerflow_health", "FAIL", str(exc))]

    if not check_agent_inventory:
        checks.append(Check("live_agent_inventory", "SKIP", "management API check disabled"))
        return checks

    try:
        response = gateway.list_agents()
    except DeerFlowError as exc:
        checks.append(Check("live_agent_inventory", "FAIL", str(exc)))
        return checks

    records = response.get("agents")
    actual = {
        str(item.get("name"))
        for item in records or []
        if isinstance(item, dict) and item.get("name")
    }
    missing = sorted(expected_agents - actual)
    checks.append(
        Check(
            "live_agent_inventory",
            "PASS" if not missing else "FAIL",
            "complete" if not missing else f"missing {missing}",
        )
    )
    return checks


def build_report(checks: list[Check]) -> dict[str, Any]:
    failures = [check for check in checks if check.status == "FAIL"]
    return {
        "status": "PASS" if not failures else "FAIL",
        "summary": {
            "pass_count": sum(check.status == "PASS" for check in checks),
            "fail_count": len(failures),
            "skip_count": sum(check.status == "SKIP" for check in checks),
        },
        "checks": [asdict(check) for check in checks],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight official DeerFlow for financial research")
    parser.add_argument("--deployment-manifest", required=True, type=Path)
    parser.add_argument("--extensions-config", required=True, type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--skip-live-agent-inventory", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    try:
        manifest = read_json(args.deployment_manifest)
        extensions = read_json(args.extensions_config)
        checks = validate_deployment_manifest(
            manifest,
            config_path=args.config,
            extensions_path=args.extensions_config,
        )
        checks.extend(validate_extensions_config(extensions))
        if args.offline:
            checks.append(Check("live_deerflow", "SKIP", "offline mode"))
        else:
            checks.extend(
                validate_live_deerflow(
                    DeerFlowGateway(),
                    set(manifest.get("expected_agents") or []),
                    check_agent_inventory=not args.skip_live_agent_inventory,
                )
            )
        report = build_report(checks)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "PASS" else 1
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
