from __future__ import annotations

from scripts import deerflow_preflight


def valid_manifest() -> dict:
    return {
        "official_repository": "bytedance/deer-flow",
        "official_ref": "v2.0.0-pinned",
        "config_version": 15,
        "sandbox_mode": "e2b",
        "sandbox_image_digest": None,
        "allow_host_bash": False,
        "memory_injection_enabled": False,
        "skill_evolution_enabled": False,
        "tool_search_enabled": True,
        "guardrails_enabled": True,
        "guardrails_fail_closed": True,
        "expected_agents": sorted(deerflow_preflight.REQUIRED_AGENTS),
        "expected_mcp_servers": ["financial-data"],
        "custom_agents_synced_at": "2026-07-01T00:00:00Z",
        "management_api_exposure": "trusted-management-network",
    }


def test_valid_deployment_manifest_passes_core_checks() -> None:
    checks = deerflow_preflight.validate_deployment_manifest(valid_manifest())
    failures = [check for check in checks if check.status == "FAIL"]
    assert failures == []


def test_unpinned_ref_and_placeholder_mcp_fail() -> None:
    manifest = valid_manifest()
    manifest["official_ref"] = "REPLACE_WITH_PINNED_TAG_OR_COMMIT"
    manifest_checks = deerflow_preflight.validate_deployment_manifest(manifest)
    assert any(
        check.name == "official_ref_pinned" and check.status == "FAIL"
        for check in manifest_checks
    )

    extension_checks = deerflow_preflight.validate_extensions_config(
        {
            "mcpServers": {
                "financial-data": {
                    "command": "python",
                    "args": ["-m", "your_financial_data_mcp_server"],
                    "enabled": True,
                }
            }
        }
    )
    assert any(
        check.name == "financial_data_mcp_placeholder_free"
        and check.status == "FAIL"
        for check in extension_checks
    )


def test_valid_financial_mcp_config_passes() -> None:
    checks = deerflow_preflight.validate_extensions_config(
        {
            "mcpServers": {
                "financial-data": {
                    "command": "uvx",
                    "args": ["approved-financial-data-mcp"],
                    "enabled": True,
                }
            }
        }
    )
    assert not [check for check in checks if check.status == "FAIL"]


def test_live_agent_inventory_detects_missing_agent() -> None:
    class FakeGateway:
        def health(self):
            return {"status": "ok"}

        def list_agents(self):
            return {
                "agents": [
                    {"name": "finance-evidence-agent"},
                    {"name": "industry-research-agent"},
                ]
            }

    checks = deerflow_preflight.validate_live_deerflow(
        FakeGateway(),
        deerflow_preflight.REQUIRED_AGENTS,
        check_agent_inventory=True,
    )
    assert any(
        check.name == "live_agent_inventory" and check.status == "FAIL"
        for check in checks
    )
