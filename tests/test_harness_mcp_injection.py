from __future__ import annotations

import asyncio

from interview_agent_runtime.harness import HarnessConfig, InterviewHarness
from interview_agent_runtime.tools import FakeMCPClient, MCPToolAdapter, MCPToolDefinition


def test_harness_loads_injected_mcp_adapters_into_tool_registry():
    asyncio.run(_case())


async def _case():
    harness = InterviewHarness.from_config(HarnessConfig.mock())
    harness.mcp_adapters = [
        MCPToolAdapter(
            FakeMCPClient(
                tools=[MCPToolDefinition("knowledge.search", "Search knowledge")]
            )
        )
    ]

    names = await harness.load_mcp_tools()

    assert names == ["mcp.knowledge.search"]
    assert harness.tool_registry.resolve("mcp.knowledge.search").spec.source == "mcp"
