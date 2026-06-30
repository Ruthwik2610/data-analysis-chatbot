from __future__ import annotations

from src.data_sources import DataSource
from backend import server
from backend.server import _wren_plan_for_source


class FakeWrenAdapter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def dry_plan(self, *, manifest, data_source, connection_info, sql):
        self.calls.append({
            "manifest": manifest,
            "data_source": data_source,
            "connection_info": connection_info,
            "sql": sql,
        })
        return f"planned::{sql}"


SCHEMA = {
    "columns": [
        {"name": "order_id", "type": "INTEGER"},
        {"name": "total_price", "type": "DOUBLE"},
    ],
    "row_count": 2,
}


def test_wren_plan_for_duckdb_source_uses_direct_engine_adapter() -> None:
    adapter = FakeWrenAdapter()
    source = DataSource(
        source_kind="DuckDB file",
        schema=SCHEMA,
        display_name="orders.duckdb",
        db_path="/tmp/datachat/orders.duckdb",
        table_name="orders",
    )

    result = _wren_plan_for_source(
        'SELECT sum(total_price) AS total FROM "orders"',
        source,
        adapter=adapter,
        enabled=True,
    )

    assert result == {
        "status": "planned",
        "data_source": "duckdb",
        "planned_sql": 'planned::SELECT sum(total_price) AS total FROM "orders"',
    }
    call = adapter.calls[0]
    assert call["data_source"] == "duckdb"
    assert call["connection_info"] == {"url": "/tmp/datachat", "format": "duckdb"}
    assert call["sql"] == 'SELECT sum(total_price) AS total FROM "orders"'
    assert call["manifest"]["dataSource"] == "duckdb"
    assert call["manifest"]["models"][0]["name"] == "orders"
    assert call["manifest"]["models"][0]["columns"][1]["name"] == "total_price"


def test_wren_plan_for_source_skips_non_duckdb_backed_sources() -> None:
    adapter = FakeWrenAdapter()
    source = DataSource(
        source_kind="Uploaded CSV",
        schema=SCHEMA,
        display_name="orders.csv",
        dataframe=None,
    )

    assert _wren_plan_for_source("SELECT 1", source, adapter=adapter, enabled=True) is None
    assert adapter.calls == []


def test_wren_plan_for_source_skips_when_disabled() -> None:
    adapter = FakeWrenAdapter()
    source = DataSource(
        source_kind="DuckDB file",
        schema=SCHEMA,
        display_name="orders.duckdb",
        db_path="/tmp/datachat/orders.duckdb",
        table_name="orders",
    )

    assert _wren_plan_for_source("SELECT 1", source, adapter=adapter, enabled=False) is None
    assert adapter.calls == []


def test_wren_plan_failure_logs_sanitized_error(monkeypatch) -> None:
    class BrokenAdapter:
        def dry_plan(self, **kwargs):
            raise RuntimeError("secret path /tmp/datachat/orders.duckdb")

    events: list[dict[str, object]] = []

    def capture_log(logger, event, **fields):
        events.append({"event": event, **fields})

    monkeypatch.setattr(server, "log_event", capture_log)
    source = DataSource(
        source_kind="DuckDB file",
        schema=SCHEMA,
        display_name="orders.duckdb",
        db_path="/tmp/datachat/orders.duckdb",
        table_name="orders",
    )

    result = _wren_plan_for_source("SELECT 1", source, adapter=BrokenAdapter(), enabled=True, request_id="req-1")

    assert result == {"status": "error", "data_source": "duckdb", "message": "Wren Engine planning failed."}
    assert events == [
        {
            "event": "wren_engine_plan_failed",
            "request_id": "req-1",
            "error_type": "RuntimeError",
        }
    ]
