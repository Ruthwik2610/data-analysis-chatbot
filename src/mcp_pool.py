"""
Persistent pool of MCP client sessions.

Every connector gets a long-lived ClientSession held open via AsyncExitStack.
Tool calls reuse the same session, not a fresh JSON-RPC round-trip per call.

All ops run on the FastAPI event loop (the lifespan task starts the pool there).
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters


HEALTH_INTERVAL_SECONDS = 600  # 10 min
CONNECT_TIMEOUT_SECONDS = 10
TOOL_CALL_TIMEOUT_SECONDS = 60


@dataclass
class ConnectorState:
    id: str
    name: str
    url: str | None = None
    command: str | None = None
    args: list[str] = field(default_factory=list)
    status: str = "connecting"  # connecting | connected | error
    last_error: str | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    _exit_stack: contextlib.AsyncExitStack | None = None
    _session: ClientSession | None = None
    # NOTE: No lock needed — all ops share a single asyncio event loop and
    # coroutines only interleave at explicit `await` points, making internal
    # mutations safe without a mutex.


def _generate_id() -> str:
    return secrets.token_hex(5)


def _tool_to_dict(tool: Any) -> dict[str, Any]:
    return {
        "name": getattr(tool, "name", ""),
        "description": getattr(tool, "description", "") or "",
        "input_schema": getattr(tool, "inputSchema", None) or {},
    }


class MCPPool:
    def __init__(self) -> None:
        self.connectors: dict[str, ConnectorState] = {}
        self._health_task: asyncio.Task[None] | None = None

    async def _open_session(
        self,
        url: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
    ) -> tuple[contextlib.AsyncExitStack, ClientSession, list[dict[str, Any]]]:
        """Open an MCP session.
        If command is provided, uses stdio transport.
        Otherwise, dispatches by URL: `/sse` → legacy SSE transport,
        anything else → Streamable HTTP with SSE as a fallback."""
        is_sse_url = url and (url.endswith("/sse") or "/sse/" in url)

        async def _try(transport: str) -> tuple[contextlib.AsyncExitStack, ClientSession, list[dict[str, Any]]]:
            stack = contextlib.AsyncExitStack()
            try:
                if transport == "stdio":
                    if not command:
                        raise ValueError("Command required for stdio transport")
                    # env=None → child inherits the full parent environment (PATH, HOME, etc.) — intentional.
                    params = StdioServerParameters(command=command, args=args or [], env=None)
                    read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
                elif transport == "sse":
                    if not url:
                        raise ValueError("URL required for sse transport")
                    streams = await stack.enter_async_context(sse_client(url))
                    read_stream, write_stream = streams[0], streams[1]
                else:
                    if not url:
                        raise ValueError("URL required for streamable_http transport")
                    streams = await stack.enter_async_context(streamablehttp_client(url))
                    read_stream, write_stream = streams[0], streams[1]

                session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
                await asyncio.wait_for(session.initialize(), timeout=CONNECT_TIMEOUT_SECONDS)
                tools_resp = await asyncio.wait_for(session.list_tools(), timeout=CONNECT_TIMEOUT_SECONDS)
                tools = [_tool_to_dict(t) for t in (tools_resp.tools or [])]
                return stack, session, tools
            except BaseException:
                await stack.aclose()
                raise

        if command:
            return await _try("stdio")

        if not url:
            raise ValueError("Either command or url must be provided")

        if is_sse_url:
            return await _try("sse")
        try:
            return await _try("streamable_http")
        except Exception as exc:
            msg = str(exc).lower()
            protocol_rejection = (
                isinstance(exc, NotImplementedError)
                or "405" in msg
                or "406" in msg
                or "method not allowed" in msg
                or "not supported" in msg
            )
            if not protocol_rejection:
                raise
            return await _try("sse")

    async def connect(
        self,
        url: str | None = None,
        name: str | None = None,
        *,
        connector_id: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
    ) -> str:
        cid = connector_id or _generate_id()
        display = name or url or command or "unnamed"
        # If reconnecting, close the existing session first.
        existing = self.connectors.get(cid)
        if existing and existing._exit_stack:
            with contextlib.suppress(Exception):
                await existing._exit_stack.aclose()

        state = ConnectorState(
            id=cid,
            name=display,
            url=url,
            command=command,
            args=args or [],
            status="connecting",
        )
        self.connectors[cid] = state
        try:
            stack, session, tools = await self._open_session(url=url, command=command, args=args)
            state._exit_stack = stack
            state._session = session
            state.tools = tools
            state.status = "connected"
            state.last_error = None
        except Exception as exc:
            state.status = "error"
            state.last_error = str(exc)
        return cid

    async def disconnect(self, connector_id: str) -> bool:
        state = self.connectors.pop(connector_id, None)
        if not state:
            return False
        if state._exit_stack:
            with contextlib.suppress(Exception):
                await state._exit_stack.aclose()
        return True

    async def rename(self, connector_id: str, name: str) -> bool:
        state = self.connectors.get(connector_id)
        if not state:
            return False
        state.name = name
        return True

    async def connect_excel(
        self,
        df: "pd.DataFrame",
        display_name: str,
        *,
        connector_id: str | None = None,
        dedup_key: str | None = None,
    ) -> str:
        from src.excel_mcp_context import ExcelMCPConnector, build_tool_name
        if dedup_key:
            for cid, s in self.connectors.items():
                if getattr(s, "_dedup_key", None) == dedup_key:
                    return cid
        slug = build_tool_name(display_name)
        exc = ExcelMCPConnector(slug=slug, df=df, display_name=display_name)
        cid = connector_id or _generate_id()
        state = ConnectorState(id=cid, name=display_name, url=None, command=None, status="connected")
        state.tools = exc.list_tools()
        state._excel_connector = exc           # type: ignore[attr-defined]
        if dedup_key:
            state._dedup_key = dedup_key       # type: ignore[attr-defined]
        self.connectors[cid] = state
        return cid

    async def call_tool(self, connector_id: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        state = self.connectors.get(connector_id)
        if not state or state.status != "connected":
            raise RuntimeError(
                f"Connector {connector_id} is not connected "
                f"(status={state.status if state else 'missing'})"
            )
        exc = getattr(state, "_excel_connector", None)
        if exc is not None:
            return await exc.call_tool(tool_name, arguments)
        if not state._session:
            raise RuntimeError(f"Connector {connector_id} has no session")
        return await asyncio.wait_for(
            state._session.call_tool(tool_name, arguments=arguments),
            timeout=TOOL_CALL_TIMEOUT_SECONDS,
        )

    def list_status(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for s in self.connectors.values():
            out.append({
                "id": s.id,
                "name": s.name,
                "url": s.url,
                "status": s.status,
                "tools": s.tools if s.status == "connected" else [],
                "last_error": s.last_error,
                "is_excel": hasattr(s, "_excel_connector"),
            })
        return out

    def aggregate_tools(self) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Returns (all_tool_specs, tool_name_to_connector_id) across all connected MCPs."""
        specs: list[dict[str, Any]] = []
        routing: dict[str, str] = {}
        for s in self.connectors.values():
            if s.status != "connected":
                continue
            for t in s.tools:
                tname = t["name"]
                if tname in routing:
                    logger.warning(
                        "MCP tool name collision: '%s' exists in connector '%s' and '%s'. "
                        "Using '%s'. Rename one tool to avoid ambiguous routing.",
                        tname, routing[tname], s.id, s.id,
                    )
                # Last-write wins on name collisions across connectors.
                routing[tname] = s.id
                specs.append({
                    "name": tname,
                    "description": t.get("description") or f"Tool from {s.name}",
                    "input_schema": t.get("input_schema") or {"type": "object", "properties": {}},
                    "connector_id": s.id,
                    "connector_name": s.name,
                })
        return specs, routing

    async def auto_load(self, registry_path: Path) -> None:
        if not registry_path.exists():
            return
        try:
            data = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception:
            return

        # Support both legacy [ {url, name}, ... ] and standard { mcpServers: { name: {command, args, url}, ... } }
        servers = []
        if isinstance(data, list):
            servers = data
        elif isinstance(data, dict):
            mcp_servers = data.get("mcpServers")
            if isinstance(mcp_servers, dict):
                for name, config in mcp_servers.items():
                    if isinstance(config, dict):
                        raw_args = config.get("args") or []
                        safe_args = list(raw_args) if isinstance(raw_args, list) else []
                        servers.append({
                            "id": name,
                            "name": name,
                            "command": config.get("command"),
                            "args": safe_args,
                            "url": config.get("url"),
                        })

        for entry in servers:
            if not isinstance(entry, dict):
                continue
            cid = entry.get("id") or entry.get("name")
            url = entry.get("url")
            command = entry.get("command")
            args = entry.get("args")
            name = entry.get("name") or cid or url or command

            if not url and not command:
                continue

            # Skip if already in the pool
            if cid and cid in self.connectors:
                continue
            if url and any(c.url == url for c in self.connectors.values()):
                continue

            await self.connect(
                url=url,
                name=name,
                connector_id=cid,
                command=command,
                args=args,
            )

    async def _health_loop(self) -> None:
        while True:
            await asyncio.sleep(HEALTH_INTERVAL_SECONDS)
            for cid, state in list(self.connectors.items()):
                if state.status == "error":
                    await self.connect(
                        url=state.url,
                        name=state.name,
                        connector_id=cid,
                        command=state.command,
                        args=state.args,
                    )
                elif state.status == "connected" and state._session:
                    # Liveness probe: verify the session (and any underlying subprocess)
                    # is still alive. A silent subprocess exit leaves status='connected'
                    # indefinitely, causing the next call_tool() to throw unexpectedly.
                    try:
                        await asyncio.wait_for(
                            state._session.list_tools(),
                            timeout=CONNECT_TIMEOUT_SECONDS,
                        )
                    except Exception as exc:
                        logger.warning(
                            "MCP connector '%s' (%s) failed liveness probe: %s — marking as error.",
                            state.name, cid, exc,
                        )
                        state.status = "error"
                        state.last_error = str(exc)

    def start_health_loop(self) -> None:
        if self._health_task is None or self._health_task.done():
            self._health_task = asyncio.create_task(self._health_loop())

    async def shutdown(self) -> None:
        if self._health_task:
            self._health_task.cancel()
            with contextlib.suppress(BaseException):
                await self._health_task
        for cid in list(self.connectors.keys()):
            await self.disconnect(cid)


_pool: MCPPool | None = None


def get_pool() -> MCPPool:
    global _pool
    if _pool is None:
        _pool = MCPPool()
    return _pool


def parse_tool_result_to_dataframe(text: str):
    """Try to coerce a tool's text result into a DataFrame.

    Accepts JSON array of objects, JSON {rows, columns}, JSON {data: [...]},
    or CSV. Returns None if nothing parses to >=1 row AND >=2 columns.
    """
    import pandas as pd

    if not text or not text.strip():
        return None
    s = text.strip()

    # Try JSON first
    try:
        data = json.loads(s)
    except Exception:
        data = None

    df = None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        df = pd.DataFrame(data)
    elif isinstance(data, dict):
        if "rows" in data and "columns" in data and isinstance(data["rows"], list):
            df = pd.DataFrame(data["rows"], columns=data["columns"])
        elif "data" in data and isinstance(data["data"], list) and data["data"] and isinstance(data["data"][0], dict):
            df = pd.DataFrame(data["data"])
        elif "results" in data and isinstance(data["results"], list) and data["results"] and isinstance(data["results"][0], dict):
            df = pd.DataFrame(data["results"])

    if df is None and "," in s and "\n" in s:
        try:
            from io import StringIO
            df = pd.read_csv(StringIO(s))
        except Exception:
            df = None

    if df is None:
        return None
    if len(df) < 1 or len(df.columns) < 2:
        return None
    return df


def extract_text_content(result: Any) -> str:
    """Pulls a plain string out of an MCP CallToolResult."""
    content = getattr(result, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if text is None and isinstance(item, dict):
                text = item.get("text")
            if text:
                parts.append(text)
        if parts:
            return "\n".join(parts)
    # Last resort: stringify whatever shape we got
    try:
        return json.dumps(content, default=str)
    except Exception:
        return str(content)
