from __future__ import annotations

import base64
import json
from pathlib import Path

import pandas as pd
import pytest

from src.wren_engine_adapter import (
    WrenEngineAdapter,
    WrenEngineUnavailable,
    build_duckdb_connection_info,
    encode_manifest,
    load_wren_engine,
)


class FakeDataSource:
    duckdb = "duckdb-enum"
    mysql = "mysql-enum"


class FakeResult:
    def to_pandas(self) -> pd.DataFrame:
        return pd.DataFrame([{"total": 42}])


class FakeEngine:
    instances: list["FakeEngine"] = []

    def __init__(self, *, manifest_str, data_source, connection_info, config=None):
        self.manifest_str = manifest_str
        self.data_source = data_source
        self.connection_info = connection_info
        self.config = config
        self.dry_plan_calls: list[str] = []
        self.dry_run_calls: list[str] = []
        self.query_calls: list[tuple[str, int | None]] = []
        FakeEngine.instances.append(self)

    def __enter__(self) -> "FakeEngine":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def dry_plan(self, sql: str) -> str:
        self.dry_plan_calls.append(sql)
        return f"planned::{sql}"

    def dry_run(self, sql: str) -> None:
        self.dry_run_calls.append(sql)

    def query(self, sql: str, limit: int | None = None) -> FakeResult:
        self.query_calls.append((sql, limit))
        return FakeResult()


MANIFEST = {
    "catalog": "wren",
    "schema": "main",
    "dataSource": "duckdb",
    "models": [],
    "relationships": [],
}


def test_encode_manifest_returns_base64_json() -> None:
    encoded = encode_manifest(MANIFEST)
    decoded = json.loads(base64.b64decode(encoded).decode("utf-8"))
    assert decoded == MANIFEST


def test_adapter_dry_plan_uses_direct_wren_engine_sdk() -> None:
    FakeEngine.instances.clear()
    adapter = WrenEngineAdapter(
        engine_cls=FakeEngine,
        data_source_enum=FakeDataSource,
        config_loader=lambda: {"loaded": True},
    )

    planned = adapter.dry_plan(
        manifest=MANIFEST,
        data_source="duckdb",
        connection_info={"url": "/tmp/data", "format": "duckdb"},
        sql='SELECT * FROM "orders"',
    )

    engine = FakeEngine.instances[-1]
    assert planned == 'planned::SELECT * FROM "orders"'
    assert json.loads(base64.b64decode(engine.manifest_str).decode("utf-8")) == MANIFEST
    assert engine.data_source == "duckdb-enum"
    assert engine.connection_info == {"url": "/tmp/data", "format": "duckdb"}
    assert engine.config == {"loaded": True}
    assert engine.dry_plan_calls == ['SELECT * FROM "orders"']


def test_adapter_supports_wren_config_loader_that_requires_home_path() -> None:
    FakeEngine.instances.clear()
    seen_paths: list[Path] = []

    def load_config(wren_home: Path):
        seen_paths.append(wren_home)
        return {"wren_home": str(wren_home)}

    adapter = WrenEngineAdapter(
        engine_cls=FakeEngine,
        data_source_enum=FakeDataSource,
        config_loader=load_config,
    )

    adapter.dry_plan(
        manifest=MANIFEST,
        data_source="duckdb",
        connection_info={"url": "/tmp/data", "format": "duckdb"},
        sql='SELECT * FROM "orders"',
    )

    assert seen_paths == [Path.home() / ".wren"]
    assert FakeEngine.instances[-1].config == {"wren_home": str(Path.home() / ".wren")}


def test_adapter_dry_run_and_query_dataframe_call_direct_engine() -> None:
    FakeEngine.instances.clear()
    adapter = WrenEngineAdapter(
        engine_cls=FakeEngine,
        data_source_enum=FakeDataSource,
        config_loader=lambda: None,
    )

    adapter.dry_run(
        manifest=MANIFEST,
        data_source="duckdb",
        connection_info={"url": "/tmp/data", "format": "duckdb"},
        sql='SELECT * FROM "orders"',
    )
    df = adapter.query_dataframe(
        manifest=MANIFEST,
        data_source="duckdb",
        connection_info={"url": "/tmp/data", "format": "duckdb"},
        sql='SELECT sum(total_price) AS total FROM "orders"',
        limit=10,
    )

    assert FakeEngine.instances[0].dry_run_calls == ['SELECT * FROM "orders"']
    assert FakeEngine.instances[1].query_calls == [
        ('SELECT sum(total_price) AS total FROM "orders"', 10)
    ]
    assert df.to_dict(orient="records") == [{"total": 42}]


def test_build_duckdb_connection_info_uses_database_directory() -> None:
    assert build_duckdb_connection_info(Path("/tmp/cache/orders.duckdb")) == {
        "url": "/tmp/cache",
        "format": "duckdb",
    }


def test_load_wren_engine_raises_actionable_error_when_package_missing() -> None:
    def missing_importer(_name: str):
        raise ImportError("not installed")

    with pytest.raises(WrenEngineUnavailable, match="pip install wren-engine==0.6.0"):
        load_wren_engine(import_module=missing_importer)
