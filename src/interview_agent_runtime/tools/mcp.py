from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Protocol, Tuple

from interview_agent_runtime.tools.registry import Tool, ToolContext, ToolRegistry, ToolSpec


@dataclass
class MCPToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )


class MCPClient(Protocol):
    async def list_tools(self) -> List[MCPToolDefinition]:
        ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        ...


class MCPToolAdapter:
    def __init__(self, client: MCPClient, *, namespace: str = "mcp") -> None:
        self.client = client
        self.namespace = namespace.strip(".")

    async def load_tools(self, registry: ToolRegistry) -> list[str]:
        names: list[str] = []
        for definition in await self.client.list_tools():
            registered_name = self._registered_name(definition.name)
            original_name = definition.name

            async def handler(
                context: ToolContext,
                args: dict[str, Any],
                *,
                tool_name: str = original_name,
            ) -> dict[str, Any]:
                value = await self.client.call_tool(tool_name, args)
                return value if isinstance(value, dict) else {"value": value}

            registry.register(
                Tool(
                    spec=ToolSpec(
                        name=registered_name,
                        description=definition.description,
                        input_schema=dict(definition.input_schema),
                        source="mcp",
                    ),
                    handler=handler,
                    metadata={
                        "source": "mcp",
                        "mcp_tool_name": original_name,
                        "namespace": self.namespace,
                    },
                )
            )
            names.append(registered_name)
        return names

    def _registered_name(self, tool_name: str) -> str:
        if tool_name.startswith(f"{self.namespace}."):
            return tool_name
        return f"{self.namespace}.{tool_name}"


class FakeMCPClient:
    def __init__(
        self,
        tools: Optional[List[MCPToolDefinition]] = None,
        responses: Optional[dict[str, Any]] = None,
    ) -> None:
        self.tools = list(tools or [])
        self.responses = dict(responses or {})
        self.calls: List[Tuple[str, dict[str, Any]]] = []

    async def list_tools(self) -> List[MCPToolDefinition]:
        return list(self.tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, dict(arguments)))
        return self.responses.get(name, {})
