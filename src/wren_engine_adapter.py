from __future__ import annotations

import base64
import inspect
import importlib
import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd


WREN_ENGINE_REQUIREMENT = "wren-engine==0.6.0"


class WrenEngineUnavailable(RuntimeError):
    """Raised when the optional Wren Engine SDK cannot be imported."""


def encode_manifest(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), default=str)
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def load_wren_engine(
    *,
    import_module: Callable[[str], Any] = importlib.import_module,
) -> tuple[type[Any], Any, Callable[[], Any]]:
    try:
        try:
            engine_module = import_module("wren.engine")
            data_source_module = import_module("wren.model.data_source")
            config_module = import_module("wren.config")
            return engine_module.WrenEngine, data_source_module.DataSource, config_module.load_config
        except (ImportError, AttributeError):
            wren_module = import_module("wren")
            return wren_module.WrenEngine, wren_module.DataSource, lambda: None
    except Exception as exc:
        raise WrenEngineUnavailable(
            f"Wren Engine SDK is not installed. Install it with `pip install {WREN_ENGINE_REQUIREMENT}`."
        ) from exc


def build_duckdb_connection_info(db_path: str | Path) -> dict[str, str]:
    path = Path(db_path)
    return {"url": str(path.parent), "format": "duckdb"}


class WrenEngineAdapter:
    def __init__(
        self,
        *,
        engine_cls: type[Any] | None = None,
        data_source_enum: Any | None = None,
        config_loader: Callable[[], Any] | None = None,
    ) -> None:
        if engine_cls is None or data_source_enum is None:
            loaded_engine, loaded_data_source, loaded_config = load_wren_engine()
            engine_cls = engine_cls or loaded_engine
            data_source_enum = data_source_enum or loaded_data_source
            config_loader = config_loader or loaded_config
        self._engine_cls = engine_cls
        self._data_source_enum = data_source_enum
        self._config_loader = config_loader or (lambda: None)

    def _load_config(self) -> Any:
        try:
            signature = inspect.signature(self._config_loader)
        except (TypeError, ValueError):
            return self._config_loader()
        required_args = [
            param
            for param in signature.parameters.values()
            if param.default is inspect.Parameter.empty
            and param.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
        ]
        if not required_args:
            return self._config_loader()
        return self._config_loader(Path.home() / ".wren")

    def _resolve_data_source(self, data_source: str) -> Any:
        attr = data_source.strip().lower()
        try:
            return getattr(self._data_source_enum, attr)
        except AttributeError as exc:
            raise ValueError(f"Unsupported Wren Engine data source: {data_source}") from exc

    def _engine(self, manifest: dict[str, Any], data_source: str, connection_info: dict[str, Any]) -> Any:
        return self._engine_cls(
            manifest_str=encode_manifest(manifest),
            data_source=self._resolve_data_source(data_source),
            connection_info=connection_info,
            config=self._load_config(),
        )

    def dry_plan(
        self,
        *,
        manifest: dict[str, Any],
        data_source: str,
        connection_info: dict[str, Any],
        sql: str,
    ) -> str:
        with self._engine(manifest, data_source, connection_info) as engine:
            return str(engine.dry_plan(sql))

    def dry_run(
        self,
        *,
        manifest: dict[str, Any],
        data_source: str,
        connection_info: dict[str, Any],
        sql: str,
    ) -> None:
        with self._engine(manifest, data_source, connection_info) as engine:
            engine.dry_run(sql)

    def query_dataframe(
        self,
        *,
        manifest: dict[str, Any],
        data_source: str,
        connection_info: dict[str, Any],
        sql: str,
        limit: int | None = None,
    ) -> pd.DataFrame:
        with self._engine(manifest, data_source, connection_info) as engine:
            table = engine.query(sql, limit=limit)
        return table.to_pandas()
