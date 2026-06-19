"""In-process MCP tool registry.

Provides a lightweight tool registration system for local MCP servers.
Tools registered here are discoverable via /api/mcp/* endpoints and
can be injected into LangGraph agents alongside external MCP tools.
"""

import json
import time
import typing as t
from dataclasses import dataclass, field


@dataclass
class MCPToolDef:
    name: str
    server: str
    description: str
    schema: dict = field(default_factory=dict)
    callable_fn: t.Callable = None


@dataclass
class MCPServerStatus:
    name: str
    transport: str = "in-process"
    connected: bool = True
    tool_count: int = 0
    error: str = ""
    description: str = ""
    server_type: str = "in-process"  # "in-process" | "external"
    optional: bool = False


class MCPToolRegistry:
    """Singleton registry for in-process MCP tools."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._servers: dict[str, MCPServerStatus] = {}
            cls._instance._tools: dict[str, MCPToolDef] = {}
            cls._instance._initialized = False
        return cls._instance

    def register_server(self, name: str, transport: str = "in-process", description: str = "") -> "MCPToolRegistry":
        self._servers[name] = MCPServerStatus(name=name, transport=transport, description=description)
        return self

    def register_tool(
        self,
        server: str,
        name: str,
        description: str,
        schema: dict = None,
        callable_fn: t.Callable = None,
    ) -> "MCPToolRegistry":
        # Ensure server is registered
        if server not in self._servers:
            self.register_server(server)
        # Build full-qualified tool name: server__tool_name
        fqn = f"{server}__{name}"
        self._tools[fqn] = MCPToolDef(
            name=fqn,
            server=server,
            description=description,
            schema=schema or {},
            callable_fn=callable_fn,
        )
        self._servers[server].tool_count = sum(
            1 for t in self._tools.values() if t.server == server
        )
        return self

    def get_status(self) -> list[dict]:
        return [
            {
                "server": s.name,
                "transport": s.transport,
                "connected": s.connected,
                "toolCount": s.tool_count,
                "error": s.error,
            }
            for s in self._servers.values()
        ]

    def get_tools(self, server: str = None) -> list[dict]:
        tools = self._tools.values()
        if server:
            tools = [t for t in tools if t.server == server]
        return [
            {
                "name": t.name,
                "server": t.server,
                "description": t.description,
                "schema": t.schema,
            }
            for t in tools
        ]

    def call_tool(self, tool_name: str, args: dict) -> dict:
        tool = self._tools.get(tool_name)
        if not tool:
            return {"error": f"tool not found: {tool_name}"}
        if not tool.callable_fn:
            return {"error": f"tool has no callable: {tool_name}"}
        try:
            start = time.time()
            result = tool.callable_fn(**args)
            latency_ms = int((time.time() - start) * 1000)
            return {
                "server": tool.server,
                "tool": tool.name,
                "latencyMs": latency_ms,
                "success": True,
                "result": result,
            }
        except Exception as e:
            return {
                "server": tool.server,
                "tool": tool.name,
                "success": False,
                "error": str(e),
            }

    def get_langchain_tools(self) -> list:
        """Return registered tools as langchain StructuredTool instances."""
        from langchain_core.tools import tool as lc_tool
        result = []
        for t in self._tools.values():
            if t.callable_fn:
                # Create a langchain tool wrapper
                fn = t.callable_fn
                wrapped = lc_tool(description=t.description)(fn)
                wrapped.name = t.name
                result.append(wrapped)
        return result


# Global singleton
mcp_registry = MCPToolRegistry()
