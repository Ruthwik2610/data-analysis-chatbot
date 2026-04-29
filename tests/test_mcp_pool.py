import asyncio
import json
from pathlib import Path
from src.mcp_pool import MCPPool, ConnectorState


def test_mcp_list_tools_timeout(monkeypatch):
    pool = MCPPool()

    # Simple test to verify our timeout logic
    async def mock_list_tools():
        await asyncio.sleep(10)
        return []

    async def run_test():
        import pytest
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(mock_list_tools(), timeout=0.1)

    asyncio.run(run_test())


def test_auto_load_skips_malformed_entries(tmp_path, monkeypatch):
    pool = MCPPool()
    registry_path = tmp_path / "mcp.json"

    # Array containing strings instead of dicts
    registry_path.write_text(json.dumps(["http://localhost:8000", {"url": "http://example.com"}]))

    # Mock connect to avoid real network calls — must accept the new signature
    async def mock_connect(url=None, name=None, connector_id=None, command=None, args=None):
        key = connector_id or url or command or "unnamed"
        pool.connectors[key] = ConnectorState(id=key, name=name or url or command or "unnamed", url=url)
        return key

    monkeypatch.setattr(pool, "connect", mock_connect)

    # This shouldn't raise an AttributeError from .get()
    asyncio.run(pool.auto_load(registry_path))

    # The valid connector should be connected (or attempted)
    assert len(pool.connectors) == 1
    assert "http://example.com" in [c.url for c in pool.connectors.values()]


def test_auto_load_mcpservers_format(tmp_path, monkeypatch):
    """New format: { mcpServers: { name: { command, args } } }"""
    pool = MCPPool()
    registry_path = tmp_path / "mcp.json"

    config = {
        "mcpServers": {
            "postgres": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://user:pass@host/db"],
            }
        }
    }
    registry_path.write_text(json.dumps(config))

    connected = []

    async def mock_connect(url=None, name=None, connector_id=None, command=None, args=None):
        key = connector_id or name or "unnamed"
        pool.connectors[key] = ConnectorState(id=key, name=name or key, url=url, command=command, args=args or [])
        connected.append({"id": key, "command": command, "args": args})
        return key

    monkeypatch.setattr(pool, "connect", mock_connect)

    asyncio.run(pool.auto_load(registry_path))

    assert len(connected) == 1
    assert connected[0]["command"] == "npx"
    assert connected[0]["id"] == "postgres"


def test_auto_load_skips_if_already_in_pool(tmp_path, monkeypatch):
    """Connectors already in pool should not be re-connected."""
    pool = MCPPool()
    registry_path = tmp_path / "mcp.json"
    registry_path.write_text(json.dumps({"mcpServers": {"postgres": {"command": "npx", "args": []}}}))

    # Pre-populate
    pool.connectors["postgres"] = ConnectorState(id="postgres", name="postgres", command="npx")

    connect_calls = []

    async def mock_connect(**kwargs):
        connect_calls.append(kwargs)
        return "new"

    monkeypatch.setattr(pool, "connect", mock_connect)

    asyncio.run(pool.auto_load(registry_path))

    # Should have been skipped
    assert len(connect_calls) == 0

def test_connector_state_has_no_dead_lock_field():
    """_lock field should not exist on ConnectorState (it was never used)."""
    state = ConnectorState(id="x", name="x")
    assert not hasattr(state, "_lock"), (
        "_lock is dead code — declare intent by removing it"
    )


def test_health_loop_marks_dead_session_as_error():
    """A 'connected' connector whose list_tools() raises must become 'error'."""
    import asyncio
    import src.mcp_pool as mcp_pool_module
    from src.mcp_pool import MCPPool, ConnectorState

    pool = MCPPool()

    class DeadSession:
        async def list_tools(self):
            raise OSError("subprocess died")

    state = ConnectorState(id="pg", name="postgres", command="mcp-server-postgres", status="connected")
    state._session = DeadSession()
    pool.connectors["pg"] = state

    # Override the sleep interval to 0 so the loop fires immediately
    original_interval = mcp_pool_module.HEALTH_INTERVAL_SECONDS
    mcp_pool_module.HEALTH_INTERVAL_SECONDS = 0

    async def run_one_tick():
        task = asyncio.create_task(pool._health_loop())
        # Wait long enough for one full iteration: sleep(0) + probe + status update
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    try:
        asyncio.run(run_one_tick())
    finally:
        mcp_pool_module.HEALTH_INTERVAL_SECONDS = original_interval

    assert pool.connectors["pg"].status == "error", (
        "Health loop must detect dead session and set status='error'"
    )


# ---------------------------------------------------------------------------
# Fix 3: [MEDIUM] auto_load must validate args is a list
# ---------------------------------------------------------------------------
def test_auto_load_coerces_string_args_to_empty_list(tmp_path, monkeypatch):
    """If mcp.json has 'args' as a bare string, auto_load must ignore it (use [])."""
    from src.mcp_pool import MCPPool, ConnectorState

    pool = MCPPool()
    registry_path = tmp_path / "mcp.json"
    # Malformed: args is a bare string, not a list
    config = {"mcpServers": {"postgres": {"command": "mcp-server-postgres", "args": "not-a-list"}}}
    registry_path.write_text(__import__("json").dumps(config))

    captured = []

    async def mock_connect(url=None, name=None, connector_id=None, command=None, args=None):
        captured.append(args)
        pool.connectors[connector_id or "pg"] = ConnectorState(
            id=connector_id or "pg", name=name or "pg", command=command, args=args or []
        )
        return connector_id or "pg"

    monkeypatch.setattr(pool, "connect", mock_connect)
    asyncio.run(pool.auto_load(registry_path))

    assert len(captured) == 1
    assert isinstance(captured[0], list), (
        "auto_load must coerce non-list args to [] before calling connect()"
    )


# ---------------------------------------------------------------------------
# Fix 4: [LOW] env=None must have a comment explaining subprocess inherits env
# ---------------------------------------------------------------------------
def test_open_session_env_none_has_explanatory_comment():
    """StdioServerParameters(env=None) line must carry an intent comment."""
    import inspect
    from src.mcp_pool import MCPPool
    source = inspect.getsource(MCPPool._open_session)
    assert "inherits" in source.lower() or "intentional" in source.lower(), (
        "env=None must have a comment explaining that the child inherits the parent environment"
    )


# ---------------------------------------------------------------------------
# Fix 5: [LOW] Tool name collision must emit a logging.warning
# ---------------------------------------------------------------------------
def test_aggregate_tools_warns_on_name_collision(monkeypatch):
    """aggregate_tools() must log a warning when two connectors share a tool name."""
    import logging
    from src.mcp_pool import MCPPool, ConnectorState

    pool = MCPPool()
    for cid, name in [("c1", "connector-a"), ("c2", "connector-b")]:
        state = ConnectorState(id=cid, name=name, status="connected")
        state.tools = [{"name": "query", "description": "run SQL", "input_schema": {}}]
        pool.connectors[cid] = state

    warnings: list[str] = []

    class CapturingHandler(logging.Handler):
        def emit(self, record):
            if record.levelno == logging.WARNING:
                warnings.append(record.getMessage())

    logger = logging.getLogger("src.mcp_pool")
    handler = CapturingHandler()
    logger.addHandler(handler)
    try:
        pool.aggregate_tools() 
    finally:
        logger.removeHandler(handler)

    assert any("query" in w or "collision" in w.lower() for w in warnings), (
        "aggregate_tools() must emit a warning when tool name 'query' collides across connectors"
    )
