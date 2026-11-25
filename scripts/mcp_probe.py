"""Exercise each installed MCP connection against public metadata without paying."""

import asyncio
import json
from pathlib import Path
import sys
import tomllib
from importlib.metadata import version

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def value(result):
    assert not result.is_error, str(result.content)
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(next(block.text for block in result.content if block.type == "text"))


def protected_keys(value):
    if isinstance(value, dict):
        return bool({"instructions", "workflow_json", "private_key"} & value.keys()) or any(protected_keys(v) for v in value.values())
    if isinstance(value, list):
        return any(protected_keys(v) for v in value)
    return False


async def main():
    configuration = tomllib.loads(Path(sys.argv[1]).read_text())
    assert configuration["model"] == "preserved"
    assert configuration["mcp_servers"]["human"]["url"] == "https://example.invalid/human"
    cases = [("realtor", "open house lead follow up", "realtor_handle_open_house_lead_follow_up"),
             ("farmer", "track equipment maintenance logs", "farmer-track-equipment-maintenance-logs"),
             ("teacher", "write daily lesson plans", "teacher-write-daily-lesson-plans")]
    reports = []
    expected_version = version("tasksai-agent-skills")
    for product, task, skill in cases:
        entry = configuration["mcp_servers"][f"tasksai-{product}-pay-per-use"]
        async with stdio_client(StdioServerParameters(command=entry["command"], args=entry["args"])) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                initialized = await session.initialize()
                assert initialized.server_info.version == expected_version
                tools = await session.list_tools()
                assert len(tools.tools) == 7
                matches = value(await session.call_tool("search_skills", {"task_summary": task, "limit": 5}))
                assert any(item["skill_id"] == skill for item in matches["matches"]), matches
                preview = value(await session.call_tool("inspect_skill", {"skill_id": skill}))
                quote = value(await session.call_tool("quote_skill", {"skill_id": skill}))
                assert quote["payment_made"] is False
                assert quote["offer"]["price"]["atomic_amount"] == "50000"
                assert not protected_keys(preview)
                assert not protected_keys(matches)
                denied = await session.call_tool("purchase_skill", {"quote_id": quote["quote_id"]})
                assert denied.is_error and "Discovery-only" in str(denied.content)
                status = value(await session.call_tool("purchase_status", {}))
                assert not status["spending_configured"] and not status["uses"]
                assert float(status["reserved_usdc"]) == 0
                with httpx.Client(timeout=60, trust_env=False, follow_redirects=False) as client:
                    response = client.get(quote["offer"]["purchase_url"])
                assert response.status_code == 402
                assert not protected_keys(response.json())
                reports.append({"product": product, "tools": len(tools.tools), "search_matched": True,
                                "quote_usdc": quote["offer"]["price"]["amount"], "unpaid_package_status": 402,
                                "unconfigured_purchase_blocked": True, "instructions_exposed": False})
    print(json.dumps({"version": expected_version, "checks": reports, "payment_made": False}))


if __name__ == "__main__":
    asyncio.run(main())
