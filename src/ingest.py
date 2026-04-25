from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from .logging_config import log_event


CACHE_VERSION = "2026-04-25-v1"
DATE_COLUMNS = {"cust_registration_date", "order_datetime", "expected_delivery", "actual_delivery"}
BOOLEAN_COLUMNS = {"is_prime_member", "is_cod", "is_returnable"}
NUMERIC_COLUMNS = {
    "cust_age",
    "lat",
    "long",
    "prod_weight_grams",
    "qty",
    "unit_price",
    "mrp_price",
    "discount_amt",
    "discount_pct",
    "taxable_val",
    "tax_rate_pct",
    "tax_amt",
    "total_order_val",
    "shipping_cost",
}


def normalize_identifier(name: str, index: int | None = None) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", name.strip()).strip("_").lower()
    if not cleaned:
        cleaned = f"unnamed_{index or 0}"
    if cleaned[0].isdigit():
        cleaned = f"col_{cleaned}"
    return cleaned


def read_header(data_path: Path) -> list[str]:
    with data_path.open(newline="", encoding="utf-8-sig") as handle:
        return next(csv.reader(handle))


def source_fingerprint(data_path: Path) -> dict[str, Any]:
    stat = data_path.stat()
    header = read_header(data_path)
    schema_hash = hashlib.sha256(json.dumps(header, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {
        "path": str(data_path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "schema_hash": schema_hash,
        "cache_version": CACHE_VERSION,
    }


def cache_paths(cache_dir: Path) -> dict[str, Path]:
    return {
        "db": cache_dir / "orders.duckdb",
        "metadata": cache_dir / "metadata.json",
        "schema": cache_dir / "schema_summary.json",
    }


def cache_is_valid(data_path: Path, cache_dir: Path) -> bool:
    paths = cache_paths(cache_dir)
    if not paths["db"].exists() or not paths["metadata"].exists():
        return False
    try:
        saved = json.loads(paths["metadata"].read_text(encoding="utf-8"))
        return saved == source_fingerprint(data_path)
    except Exception:
        return False


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def transform_expression(raw_column: str, clean_column: str) -> str:
    src = quote_ident(raw_column)
    alias = quote_ident(clean_column)
    trimmed = f"NULLIF(TRIM(CAST({src} AS VARCHAR)), '')"
    if clean_column in DATE_COLUMNS:
        return f"try_strptime({trimmed}, ['%d-%m-%Y %H:%M', '%d-%m-%Y']) AS {alias}"
    if clean_column in BOOLEAN_COLUMNS:
        return f"CASE WHEN upper({trimmed}) = 'TRUE' THEN TRUE WHEN upper({trimmed}) = 'FALSE' THEN FALSE ELSE NULL END AS {alias}"
    if clean_column in NUMERIC_COLUMNS:
        return f"TRY_CAST(regexp_replace({trimmed}, '[^0-9.-]', '', 'g') AS DOUBLE) AS {alias}"
    if clean_column in {"cust_phone", "tracking_no"}:
        return f"ltrim({trimmed}, '''') AS {alias}"
    return f"{trimmed} AS {alias}"


def ensure_cache(data_path: Path, cache_dir: Path, logger: Any | None = None, force: bool = False) -> dict[str, Any]:
    if not data_path.exists():
        raise FileNotFoundError(f"CSV not found: {data_path}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths = cache_paths(cache_dir)
    if not force and cache_is_valid(data_path, cache_dir):
        return load_schema_summary(cache_dir)

    try:
        import duckdb
    except Exception as exc:  # pragma: no cover - dependency availability
        raise RuntimeError("DuckDB is required. Install requirements.txt first.") from exc

    start = time.perf_counter()
    tmp_db = paths["db"].with_suffix(".tmp.duckdb")
    if tmp_db.exists():
        tmp_db.unlink()
    con = duckdb.connect(str(tmp_db))
    try:
        con.execute(
            """
            CREATE OR REPLACE TABLE raw_orders AS
            SELECT * FROM read_csv_auto(?, header=true, all_varchar=true, ignore_errors=false)
            """,
            [str(data_path)],
        )
        raw_columns = [row[1] for row in con.execute("PRAGMA table_info(raw_orders)").fetchall()]
        header = read_header(data_path)
        clean_pairs: list[tuple[str, str]] = []
        for index, raw_col in enumerate(raw_columns):
            original = header[index] if index < len(header) else raw_col
            if not original.strip():
                continue
            clean = normalize_identifier(original, index)
            clean_pairs.append((raw_col, clean))
        expressions = [transform_expression(raw, clean) for raw, clean in clean_pairs]
        con.execute(f"CREATE OR REPLACE TABLE orders AS SELECT {', '.join(expressions)} FROM raw_orders")
        con.execute("DROP TABLE raw_orders")
        row_count = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        schema = profile_schema(con, row_count)
        paths["schema"].write_text(json.dumps(schema, indent=2, default=str), encoding="utf-8")
        paths["metadata"].write_text(json.dumps(source_fingerprint(data_path), indent=2), encoding="utf-8")
        con.close()
        if paths["db"].exists():
            paths["db"].unlink()
        tmp_db.rename(paths["db"])
        if logger:
            log_event(logger, "cache_rebuilt", rows=row_count, elapsed_ms=int((time.perf_counter() - start) * 1000))
        return schema
    except Exception:
        con.close()
        if tmp_db.exists():
            tmp_db.unlink()
        raise


def profile_schema(con: Any, row_count: int) -> dict[str, Any]:
    columns = [{"name": row[1], "type": row[2]} for row in con.execute("PRAGMA table_info(orders)").fetchall()]
    categorical = [
        "order_status",
        "payment_mode",
        "prod_category",
        "prod_subcategory",
        "cust_segment",
        "ship_country",
        "ship_city",
        "carrier_name",
        "device_type",
    ]
    examples: dict[str, list[Any]] = {}
    column_names = {col["name"] for col in columns}
    for col in categorical:
        if col in column_names:
            rows = con.execute(f"SELECT {quote_ident(col)}, COUNT(*) AS n FROM orders GROUP BY 1 ORDER BY n DESC LIMIT 8").fetchall()
            examples[col] = [value for value, _ in rows]
    return {
        "table": "orders",
        "row_count": row_count,
        "columns": columns,
        "examples": examples,
        "notes": [
            "Each row is treated as one ecommerce order/product record.",
            "Use total_order_val for revenue questions.",
            "Use order_datetime for time trends.",
            "Use DuckDB for all calculations; do not answer from memory.",
        ],
    }


def load_schema_summary(cache_dir: Path) -> dict[str, Any]:
    return json.loads(cache_paths(cache_dir)["schema"].read_text(encoding="utf-8"))


def schema_from_dataframe(df: Any, source_name: str = "in_memory") -> dict[str, Any]:
    columns = [{"name": str(name), "type": str(dtype)} for name, dtype in df.dtypes.items()]
    examples: dict[str, list[Any]] = {}
    for col in df.columns[:80]:
        if df[col].dtype == "object" or str(df[col].dtype).startswith("category"):
            values = [value for value in df[col].dropna().astype(str).value_counts().head(8).index.tolist()]
            if values:
                examples[str(col)] = values
    return {
        "table": "orders",
        "row_count": int(len(df)),
        "columns": columns,
        "examples": examples,
        "notes": [
            f"Source: {source_name}.",
            "This source is queried through an in-memory DuckDB table named orders.",
            "Use DuckDB for all calculations; do not answer from memory.",
        ],
    }


def schema_from_duckdb(con: Any, table_name: str = "orders") -> dict[str, Any]:
    safe_table = quote_ident(table_name)
    row_count = con.execute(f"SELECT COUNT(*) FROM {safe_table}").fetchone()[0]
    columns = [{"name": row[1], "type": row[2]} for row in con.execute(f"PRAGMA table_info({safe_table})").fetchall()]
    return {
        "table": table_name,
        "row_count": row_count,
        "columns": columns,
        "examples": {},
        "notes": [
            f"Source: DuckDB table {table_name}.",
            "Queries are run against this table through a view named orders.",
            "Use DuckDB for all calculations; do not answer from memory.",
        ],
    }
