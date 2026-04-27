"""
Persistent pool of MCP client sessions.

Mirrors the DMV-connect Node.js architecture: every connector gets a long-lived
ClientSession held open via AsyncExitStack. Tool calls reuse the same session,
not a fresh JSON-RPC round-trip per call.

All ops run on the FastAPI event loop (the lifespan task starts the pool there).
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.sse import sse_client


HEALTH_INTERVAL_SECONDS = 600  # 10 min, matches DMV
CONNECT_TIMEOUT_SECONDS = 20
TOOL_CALL_TIMEOUT_SECONDS = 60


@dataclass
class ConnectorState:
    id: str
    url: str
    name: str
    status: str = "connecting"  # connecting | connected | error
    last_error: str | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    _exit_stack: contextlib.AsyncExitStack | None = None
    _session: ClientSession | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)


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

    async def _open_session(self, url: str) -> tuple[contextlib.AsyncExitStack, ClientSession, list[dict[str, Any]]]:
        """Open an MCP session. Dispatches by URL: `/sse` → legacy SSE transport,
        anything else → Streamable HTTP with SSE as a fallback."""
        is_sse_url = url.endswith("/sse") or "/sse/" in url

        async def _try(transport: str) -> tuple[contextlib.AsyncExitStack, ClientSession, list[dict[str, Any]]]:
            stack = contextlib.AsyncExitStack()
            try:
                if transport == "sse":
                    streams = await stack.enter_async_context(sse_client(url))
                else:
                    streams = await stack.enter_async_context(streamablehttp_client(url))
                # streamablehttp_client returns 3-tuple (read, write, get_session_id);
                # sse_client returns 2-tuple. Take the first two either way.
                read_stream, write_stream = streams[0], streams[1]
                session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
                await asyncio.wait_for(session.initialize(), timeout=CONNECT_TIMEOUT_SECONDS)
                tools_resp = await session.list_tools()
                tools = [_tool_to_dict(t) for t in (tools_resp.tools or [])]
                return stack, session, tools
            except BaseException:
                await stack.aclose()
                raise

        if is_sse_url:
            return await _try("sse")
        try:
            return await _try("streamable_http")
        except Exception as exc:
            # Only fall back when the server appears to reject Streamable HTTP at the
            # protocol level (405/406/"not supported"). Network errors, timeouts, and
            # auth failures should propagate so the real cause isn't masked.
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

    async def connect(self, url: str, name: str | None = None, *, connector_id: str | None = None) -> str:
        cid = connector_id or _generate_id()
        display = name or url
        # If reconnecting, close the existing session first.
        existing = self.connectors.get(cid)
        if existing and existing._exit_stack:
            with contextlib.suppress(Exception):
                await existing._exit_stack.aclose()
        state = ConnectorState(id=cid, url=url, name=display, status="connecting")
        self.connectors[cid] = state
        try:
            stack, session, tools = await self._open_session(url)
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

    async def call_tool(self, connector_id: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        state = self.connectors.get(connector_id)
        if not state or state.status != "connected" or not state._session:
            raise RuntimeError(f"Connector {connector_id} is not connected (status={state.status if state else 'missing'})")
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
                # Last-write wins on name collisions across connectors. DMV does the same.
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
            entries = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(entries, list):
            return
        for entry in entries:
            url = entry.get("url")
            name = entry.get("name") or entry.get("id") or url
            if not url:
                continue
            # Skip if a connector for this URL is already in the pool — name is a display label, URL is identity.
            if any(c.url == url for c in self.connectors.values()):
                continue
            await self.connect(url, name)

    async def _health_loop(self) -> None:
        while True:
            await asyncio.sleep(HEALTH_INTERVAL_SECONDS)
            for cid, state in list(self.connectors.items()):
                if state.status == "error":
                    await self.connect(state.url, state.name, connector_id=cid)

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
    or CSV. Returns None if nothing parses to >=2 rows AND >=2 columns.
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
    if len(df) < 2 or len(df.columns) < 2:
        return None
    return df


def extract_text_content(result: Any) -> str:
    """Pulls a plain string out of an MCP CallToolResult — mirrors DMV's extractMcpContent."""
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
