"""
MCP (Model Context Protocol) Client Manager.

Provides integration between MCP servers and LangGraph agents.
Connects to MCP servers via stdio or SSE transport, discovers tools,
and wraps them as langchain-compatible StructuredTool instances.

Gracefully degrades when the ``mcp`` package is not installed.
"""

import asyncio
import json
import logging
import os
import re
import threading
import typing as t


def _resolve_env(value: str) -> str:
    """Resolve ``${VAR}`` and ``${VAR:default}`` patterns in a string."""
    def _replacer(m):
        var = m.group(1)
        default = m.group(2)
        if default is not None:
            return os.environ.get(var, default)
        return os.environ.get(var, "")
    return re.sub(r'\$\{(\w+)(?::([^}]*))?\}', _replacer, value)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conditional import of the 'mcp' third-party package
# ---------------------------------------------------------------------------
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client

    MCP_AVAILABLE = True
    _MCP_IMPORT_ERROR: str | None = None
except ImportError as _exc:
    MCP_AVAILABLE = False
    ClientSession = StdioServerParameters = stdio_client = sse_client = None
    _MCP_IMPORT_ERROR = str(_exc)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------
class MCPConnectionError(Exception):
    """Raised when an MCP server connection or tool call fails."""
    pass


# ===================================================================
# Internal: _ServerConnection
# ===================================================================
class _ServerConnection:
    """
    Manages a single MCP server in a background daemon thread.

    Each connection gets its own ``asyncio`` event loop so that the
    (async) ``mcp`` SDK can be used from a synchronous application
    (Flask / LangGraph) without blocking.
    """

    __slots__ = (
        "name",
        "config",
        "_loop",
        "_thread",
        "_session",
        "_stream_ctx",
        "_streams",
        "_ready",
        "_connected",
    )

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._session: t.Any = None
        self._stream_ctx: t.Any = None
        self._streams: tuple | None = None
        self._ready = threading.Event()
        self._connected = False

    # -- public properties --------------------------------------------------

    @property
    def connected(self) -> bool:
        """Whether the server is currently connected."""
        return self._connected and self._session is not None

    # -- public API ---------------------------------------------------------

    def start(self, timeout: float = 15.0) -> bool:
        """Connect to the server in a background daemon thread.

        Returns ``True`` if the connection was established, ``False`` if it
        timed out or failed.
        """
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"mcp-{self.name}",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=timeout):
            logger.warning(
                "MCP server '%s' did not become ready within %.1fs",
                self.name, timeout,
            )
            return False
        return self._connected

    def list_tools(self, timeout: float = 10.0) -> list:
        """Return the list of MCP ``Tool`` objects discovered from the server.

        Returns an empty list if the server is not connected.
        """
        if not self.connected:
            return []
        result = self._run_async(self._session.list_tools(), timeout)
        return list(result.tools)

    def call_tool(self, name: str, arguments: dict, timeout: float = 30.0) -> t.Any:
        """Call an MCP tool by name and return its result.

        Raises :class:`MCPConnectionError` if the server is not connected
        or the operation times out.
        """
        if not self.connected:
            raise MCPConnectionError(f"MCP server '{self.name}' is not connected")
        return self._run_async(self._session.call_tool(name, arguments), timeout)

    def stop(self):
        """Shut down the event loop and thread gracefully."""
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._connected = False
        self._session = None

    # -- internal: async bridging -------------------------------------------

    def _run_async(self, coro, timeout: float):
        """Schedule a coroutine on the server's event loop and block for the result."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout)
        except asyncio.TimeoutError:
            raise MCPConnectionError(
                f"Operation timed out on MCP server '{self.name}' after {timeout}s",
            )

    def _run_loop(self):
        """Target entrypoint for the daemon thread."""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._do_connect())
        except RuntimeError:
            # Event loop stopped during connect (expected during shutdown)
            pass
        except Exception as exc:
            logger.warning("MCP server '%s' connection failed: %s", self.name, exc)
        finally:
            self._ready.set()
        if self._connected:
            try:
                self._loop.run_forever()
            except RuntimeError:
                pass

    async def _do_connect(self):
        """Establish the MCP session."""
        transport = self.config.get("transport", "stdio")
        try:
            if transport == "stdio":
                await self._connect_stdio()
            elif transport == "sse":
                await self._connect_sse()
            else:
                logger.warning(
                    "Unknown transport '%s' for server '%s'", transport, self.name,
                )
                return
        except Exception as exc:
            logger.warning("MCP server '%s' connect error: %s", self.name, exc)
            return

        await self._session.initialize()
        self._connected = True
        logger.info(
            "MCP server '%s' connected (transport=%s)", self.name, transport,
        )

    async def _connect_stdio(self):
        """Connect via stdio transport (subprocess stdin/stdout)."""
        params = StdioServerParameters(
            command=self.config["command"],
            args=self.config.get("args", []),
            env=self.config.get("env"),
        )
        self._stream_ctx = stdio_client(params)
        self._streams = await self._stream_ctx.__aenter__()
        self._session = await ClientSession(*self._streams).__aenter__()

    async def _connect_sse(self):
        """Connect via SSE transport (HTTP Server-Sent Events)."""
        url = _resolve_env(self.config["url"])
        raw_headers = self.config.get("headers") or {}
        headers = {k: _resolve_env(v) for k, v in raw_headers.items()} if raw_headers else None
        self._stream_ctx = sse_client(url, headers=headers)
        self._streams = await self._stream_ctx.__aenter__()
        self._session = await ClientSession(*self._streams).__aenter__()


# ===================================================================
# Schema helpers (MCP JSON Schema -> Pydantic v1 model)
# ===================================================================
def _resolve_py_type(prop_schema: dict) -> type:
    """Map a JSON Schema property type to a Python type."""
    mapping: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    raw_type = prop_schema.get("type", "string")
    if isinstance(raw_type, list):
        # Union types like ["string", "null"]
        for t_item in raw_type:
            if t_item != "null":
                return mapping.get(t_item, str)
        return type(None)
    return mapping.get(raw_type, str)


def _build_args_schema(tool_name: str, input_schema: dict | None):
    """Build a Pydantic v2 ``BaseModel`` dynamically from a JSON Schema dict.

    This allows ``StructuredTool.from_function`` to present the MCP tool's
    expected arguments to the LLM in a structured way, rather than dumping
    everything into ``**kwargs``.
    """
    try:
        from pydantic import BaseModel, Field
    except ImportError:
        from langchain_core.pydantic_v1 import BaseModel, Field

    properties = (input_schema or {}).get("properties", {})
    required = set((input_schema or {}).get("required", []))

    if not properties:
        # No parameters expected
        class _EmptyArgs(BaseModel):
            pass
        return _EmptyArgs

    annotations: dict[str, type] = {}
    fields: dict[str, t.Any] = {}

    for prop_name, prop_schema in properties.items():
        py_type = _resolve_py_type(prop_schema)
        desc = prop_schema.get("description", prop_name)
        annotations[prop_name] = py_type if prop_name in required else t.Optional[py_type]
        fields[prop_name] = Field(
            description=desc,
            default=... if prop_name in required else None,
        )

    return type(
        f"{tool_name}Args",
        (BaseModel,),
        {"__annotations__": annotations, **fields},
    )


# ===================================================================
# Public manager
# ===================================================================
class MCPClientManager:
    """Manager for multiple MCP server connections.

    Loads server definitions from a JSON configuration file, connects to each
    server, discovers available tools, and wraps them as langchain-compatible
    ``StructuredTool`` instances that can be passed to LangGraph agents.

    Usage::

        from utils.mcp_client import MCPClientManager

        manager = MCPClientManager("config/mcp_servers.json")
        manager.connect_all()
        tools = manager.get_mcp_tools()          # list[StructuredTool]
        ok, msg = manager.test_mcp_connection("apifox")
        manager.disconnect_all()
    """

    def __init__(self, config_path: str | os.PathLike | None = None):
        self._config_path: str | None = str(config_path) if config_path else None
        self._config: dict[str, dict] = {}
        self._connections: dict[str, _ServerConnection] = {}
        self._loaded = False

        if config_path:
            self.load_config(config_path)

    # -- config loading -----------------------------------------------------

    def load_config(self, config_path: str | os.PathLike):
        """Load server definitions from a JSON file.

        The file should contain a top-level ``"servers"`` key mapping server
        names to their configuration objects.  For backward compatibility a
        flat dict at the root is also accepted.
        """
        path = str(config_path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            logger.warning("MCP config file not found: %s", path)
            return
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON in MCP config %s: %s", path, exc)
            return

        # Accept both {"servers": {...}} and a flat {...}
        servers = raw.get("servers", raw) if isinstance(raw, dict) else {}
        if not isinstance(servers, dict):
            logger.warning(
                "MCP config must contain a 'servers' dict, got %s",
                type(servers).__name__,
            )
            return

        self._config = servers
        self._loaded = True
        logger.info("Loaded %d MCP server(s) from %s", len(servers), path)

    # -- connection lifecycle -----------------------------------------------

    def connect_all(self) -> dict[str, bool]:
        """Connect to every configured server.

        Returns a dict mapping server names to connection success (``bool``).
        Connections that fail are logged as warnings and skipped — the
        application continues without them.
        """
        if not MCP_AVAILABLE:
            logger.warning(
                "mcp package is not installed (%s). Skipping all MCP connections.",
                _MCP_IMPORT_ERROR,
            )
            return {name: False for name in self._config}

        results: dict[str, bool] = {}
        for name, cfg in self._config.items():
            # Skip in-process servers — they are handled by the
            # in-process MCPToolRegistry directly.
            if cfg.get("transport") == "in-process":
                results[name] = True
                continue
            ok = self._connect_server(name, cfg)
            results[name] = ok
        return results

    def _connect_server(self, name: str, cfg: dict) -> bool:
        """Connect to a single server and register it on success."""
        conn = _ServerConnection(name, cfg)
        ok = conn.start()
        if ok:
            self._connections[name] = conn
        else:
            logger.warning(
                "MCP server '%s' is unreachable — continuing without it", name,
            )
        return ok

    def disconnect_all(self):
        """Disconnect from every MCP server."""
        for conn in self._connections.values():
            try:
                conn.stop()
            except Exception:
                logger.exception("Error stopping MCP connection '%s'", conn.name)
        self._connections.clear()
        logger.info("All MCP connections closed")

    def is_connected(self, server_name: str) -> bool:
        """Check whether a specific server is currently connected."""
        conn = self._connections.get(server_name)
        return conn is not None and conn.connected

    # -- tool discovery & wrapping ------------------------------------------

    def get_mcp_tools(self) -> list:
        """Discover tools from all connected MCP servers.

        Returns a list of langchain ``StructuredTool`` instances, one per MCP
        tool.  Tool names are prefixed with ``{server_name}__`` to avoid
        collisions when multiple servers expose tools with the same name.

        Returns an empty list if no servers are connected or the ``mcp``
        package is not installed.
        """
        if not MCP_AVAILABLE:
            return []

        tools: list = []
        for server_name, conn in list(self._connections.items()):
            if not conn.connected:
                continue
            try:
                mcp_tools = conn.list_tools()
            except MCPConnectionError as exc:
                logger.warning(
                    "Could not list tools from '%s': %s", server_name, exc,
                )
                continue

            for mcp_tool in mcp_tools:
                try:
                    lt = self._to_langchain_tool(server_name, mcp_tool, conn)
                    tools.append(lt)
                except Exception as exc:
                    logger.warning(
                        "Failed to wrap MCP tool '%s/%s': %s",
                        server_name, mcp_tool.name, exc,
                    )
        return tools

    def _to_langchain_tool(self, server_name: str, mcp_tool, conn: _ServerConnection):
        """Wrap a single MCP ``Tool`` as a langchain ``StructuredTool``."""
        from langchain_core.tools import StructuredTool

        prefixed_name = f"{server_name}__{mcp_tool.name}"
        desc = mcp_tool.description or mcp_tool.name
        full_desc = f"[{server_name}] {desc}"
        schema_dict = getattr(mcp_tool, "inputSchema", None)
        args_schema = _build_args_schema(prefixed_name, schema_dict)
        tool_name = mcp_tool.name

        def _execute(**kwargs: t.Any) -> str:
            """Execute the MCP tool and return a JSON string."""
            try:
                result = conn.call_tool(tool_name, kwargs)
            except MCPConnectionError as exc:
                return json.dumps(
                    {"success": False, "error": str(exc)},
                    ensure_ascii=False,
                )
            except Exception as exc:
                return json.dumps(
                    {"success": False, "error": f"Unexpected error: {exc}"},
                    ensure_ascii=False,
                )

            # Normalise the MCP CallToolResult to a simple JSON structure
            if hasattr(result, "content"):
                texts: list[str] = []
                for item in result.content:
                    if hasattr(item, "text") and item.text:
                        texts.append(item.text)
                    elif hasattr(item, "data"):
                        texts.append(str(item.data))
                    else:
                        texts.append(str(item))
                return json.dumps(
                    {"success": True, "content": texts},
                    ensure_ascii=False,
                )
            return json.dumps(
                {"success": True, "content": str(result)},
                ensure_ascii=False,
            )

        return StructuredTool.from_function(
            name=prefixed_name,
            description=full_desc,
            func=_execute,
            args_schema=args_schema,
        )

    # -- health check -------------------------------------------------------

    def test_mcp_connection(self, server_name: str) -> tuple[bool, str]:
        """Perform a one-shot health check for a specific MCP server.

        This creates a **fresh** connection (separate from the persistent one
        managed by ``connect_all``) so it works even if the long-lived
        connection has drifted.

        Returns ``(success, message)``.
        """
        if not MCP_AVAILABLE:
            return False, f"mcp package not installed ({_MCP_IMPORT_ERROR})"

        cfg = self._config.get(server_name)
        if not cfg:
            return False, f"Server '{server_name}' not found in config"

        conn = _ServerConnection(server_name, cfg)
        try:
            ok = conn.start(timeout=10.0)
            if not ok:
                return False, f"Connection to '{server_name}' timed out"

            tools = conn.list_tools(timeout=5.0)
            count = len(tools)
            return True, f"Connected to '{server_name}', discovered {count} tool(s)"
        except Exception as exc:
            return False, f"Health-check for '{server_name}' failed: {exc}"
        finally:
            conn.stop()

    @property
    def connected_servers(self) -> list[str]:
        """Return the names of servers that are currently connected."""
        return [name for name, conn in self._connections.items() if conn.connected]
