from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .ingest import cache_paths, ensure_cache, normalize_identifier, schema_from_dataframe, schema_from_duckdb
from .logging_config import log_event


@dataclass
class DataSource:
    source_kind: str
    schema: dict[str, Any]
    display_name: str
    db_path: str | None = None
    memory_key: str | None = None
    table_name: str = "orders"
    dataframe: pd.DataFrame | None = None

    @property
    def allowed_columns(self) -> set[str]:
        return {col["name"] for col in self.schema.get("columns", [])}

    @property
    def row_count(self) -> int:
        return int(self.schema.get("row_count", 0))


def normalize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    seen: dict[str, int] = {}
    for index, column in enumerate(df.columns):
        name = normalize_identifier(str(column), index)
        count = seen.get(name, 0)
        seen[name] = count + 1
        if count:
            name = f"{name}_{count + 1}"
        renamed[column] = name
    return df.rename(columns=renamed)


_DATE_NAME_HINTS = ("date", "datetime", "_at", "delivery", "timestamp", "_time")


def coerce_date_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            continue
        if df[col].dtype != object:
            continue
        lower = col.lower()
        if not any(hint in lower for hint in _DATE_NAME_HINTS):
            continue
        non_null = df[col].dropna()
        if non_null.empty:
            continue
        # Try both US (MM-DD-YYYY) and day-first (DD-MM-YYYY) parsings; pick whichever parses more.
        us_parsed = pd.to_datetime(non_null, errors="coerce", utc=False)
        df_parsed = pd.to_datetime(non_null, errors="coerce", utc=False, dayfirst=True)
        us_ok = int(us_parsed.notna().sum())
        df_ok = int(df_parsed.notna().sum())
        best_ok = max(us_ok, df_ok)
        # Only convert if at least half the non-null values look like dates.
        if best_ok < max(1, len(non_null) // 2):
            continue
        dayfirst = df_ok > us_ok
        df[col] = pd.to_datetime(df[col], errors="coerce", utc=False, dayfirst=dayfirst)
    return df


def coerce_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if df[col].dtype != object:
            continue
        non_null = df[col].dropna().astype(str).str.strip()
        if non_null.empty:
            continue
        cleaned = non_null.str.replace(r"[$,\s]", "", regex=True)
        parsed = pd.to_numeric(cleaned, errors="coerce")
        if int(parsed.notna().sum()) < max(1, len(non_null) // 2):
            continue
        full_cleaned = df[col].astype(str).str.strip().str.replace(r"[$,\s]", "", regex=True)
        df[col] = pd.to_numeric(full_cleaned, errors="coerce")
    return df


def _table_to_dataframe(table: list[list[Any]]) -> pd.DataFrame | None:
    cleaned_rows: list[list[str]] = []
    for row in table:
        values = ["" if value is None else str(value).strip() for value in row]
        if any(values):
            cleaned_rows.append(values)
    if len(cleaned_rows) < 2:
        return None
    width = max(len(row) for row in cleaned_rows)
    normalized_rows = [row + [""] * (width - len(row)) for row in cleaned_rows]
    header = normalized_rows[0]
    body = [row for row in normalized_rows[1:] if any(cell.strip() for cell in row)]
    if not body:
        return None
    df = pd.DataFrame(body, columns=header)
    return df.replace("", pd.NA).dropna(axis=1, how="all")


def read_pdf_tables(pdf_path: Path) -> pd.DataFrame:
    try:
        import pdfplumber
    except Exception as exc:  # pragma: no cover - dependency availability
        raise RuntimeError("PDF table extraction requires pdfplumber. Install requirements.txt first.") from exc

    frames: list[pd.DataFrame] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                df = _table_to_dataframe(table)
                if df is not None and not df.empty:
                    frames.append(df)
    if not frames:
        raise ValueError(
            "No tables found in this PDF. If it is a scanned/image PDF, run OCR or export the sheet as CSV/XLSX first.",
        )
    return pd.concat(frames, ignore_index=True, sort=False)


def prepare_csv_source(data_path: Path, cache_dir: Path, logger: Any, force: bool) -> DataSource:
    schema = ensure_cache(data_path, cache_dir, logger=logger, force=force)
    return DataSource(source_kind="CSV cache", schema=schema, display_name=data_path.name, db_path=str(cache_paths(cache_dir)["db"]))


def prepare_csv_memory_source(csv_path: Path, logger: Any) -> DataSource:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    import duckdb

    # DuckDB's CSV reader is ~5-10x faster than pandas on large files and infers types better.
    df = duckdb.read_csv(str(csv_path)).to_df()
    df = normalize_dataframe_columns(df)
    df = coerce_date_columns(df)
    memory_key = f"csv-memory::{csv_path.resolve()}::{csv_path.stat().st_mtime_ns}"
    schema = schema_from_dataframe(df, source_name="Uploaded CSV")
    log_event(logger, "csv_loaded_in_memory", rows=len(df), columns=len(df.columns), path=str(csv_path))
    return DataSource(source_kind="Uploaded CSV", schema=schema, display_name=csv_path.name, memory_key=memory_key, dataframe=df)


def _read_xlsx_via_duckdb(excel_path: Path, sheet: str | int) -> pd.DataFrame:
    # DuckDB's excel extension reads cell formatting metadata, so dates land as DATE/TIMESTAMP
    # and numbers as DOUBLE/BIGINT — types that pandas+openpyxl drops on the floor.
    import duckdb

    con = duckdb.connect()
    try:
        try:
            con.execute("LOAD excel")
        except Exception:
            con.execute("INSTALL excel")
            con.execute("LOAD excel")
        if isinstance(sheet, int):
            sheet_names = pd.ExcelFile(excel_path).sheet_names
            sheet_name = sheet_names[sheet] if 0 <= sheet < len(sheet_names) else sheet_names[0]
        else:
            sheet_name = str(sheet)
        return con.execute(
            "SELECT * FROM read_xlsx(?, header=true, ignore_errors=true, sheet=?)",
            [str(excel_path), sheet_name],
        ).df()
    finally:
        con.close()


def prepare_excel_source(excel_path: Path, sheet_name: str | int | None, logger: Any) -> DataSource:
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_path}")
    selected_sheet: str | int = 0 if sheet_name in {None, ""} else sheet_name
    if excel_path.suffix.lower() == ".xlsx":
        df = _read_xlsx_via_duckdb(excel_path, selected_sheet)
    else:
        # Legacy .xls — DuckDB's excel extension only reads .xlsx, so fall back to pandas.
        df = pd.read_excel(excel_path, sheet_name=selected_sheet)
    df = normalize_dataframe_columns(df)
    df = coerce_date_columns(df)
    memory_key = f"excel::{excel_path.resolve()}::{excel_path.stat().st_mtime_ns}::{selected_sheet}"
    schema = schema_from_dataframe(df, source_name=f"Excel sheet {selected_sheet}")
    log_event(logger, "excel_loaded_in_memory", rows=len(df), columns=len(df.columns), path=str(excel_path))
    return DataSource(source_kind="Excel direct", schema=schema, display_name=excel_path.name, memory_key=memory_key, dataframe=df)


def prepare_pdf_source(pdf_path: Path, logger: Any) -> DataSource:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    df = read_pdf_tables(pdf_path)
    df = normalize_dataframe_columns(df)
    df = coerce_numeric_columns(df)
    df = coerce_date_columns(df)
    memory_key = f"pdf::{pdf_path.resolve()}::{pdf_path.stat().st_mtime_ns}"
    schema = schema_from_dataframe(df, source_name="PDF tables")
    if logger:
        log_event(logger, "pdf_loaded_in_memory", rows=len(df), columns=len(df.columns), path=str(pdf_path))
    return DataSource(source_kind="PDF table", schema=schema, display_name=pdf_path.name, memory_key=memory_key, dataframe=df)


def prepare_duckdb_source(db_path: Path, table_name: str, logger: Any) -> DataSource:
    if not db_path.exists():
        raise FileNotFoundError(f"DuckDB file not found: {db_path}")
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        schema = schema_from_duckdb(con, table_name=table_name)
    finally:
        con.close()
    log_event(logger, "duckdb_source_ready", path=str(db_path), table=table_name)
    return DataSource(source_kind="DuckDB file", schema=schema, display_name=db_path.name, db_path=str(db_path), table_name=table_name)


def prepare_api_source(api_url: str, logger: Any, auth_header: str | None = None) -> DataSource:
    if not api_url:
        raise ValueError("API URL is required.")
    import requests

    headers = {}
    if auth_header:
        token = auth_header.strip()
        headers["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    response = requests.get(api_url, timeout=30, headers=headers)
    response.raise_for_status()
    payload = response.json()
    records = payload if isinstance(payload, list) else payload.get("data", payload.get("records", []))
    if not isinstance(records, list) or not records:
        raise ValueError("API response must be a non-empty JSON list or contain data/records.")
    df = normalize_dataframe_columns(pd.DataFrame(records))
    df = coerce_date_columns(df)
    memory_key = f"api::{api_url}::{hash(json.dumps(records[:25], default=str))}"
    schema = schema_from_dataframe(df, source_name="API JSON response")
    log_event(logger, "api_loaded_in_memory", rows=len(df), columns=len(df.columns), url=api_url)
    return DataSource(source_kind="API direct", schema=schema, display_name=api_url, memory_key=memory_key, dataframe=df)


def dataframe_to_duckdb_source(df: pd.DataFrame, cache_dir: Path, logger: Any, display_name: str, source_kind: str) -> DataSource:
    import duckdb

    sql_dir = cache_dir / "sql_sources"
    sql_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in Path(display_name).stem) or "source"
    db_path = sql_dir / f"{safe_name}.duckdb"
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    try:
        con.register("source_df", df)
        con.execute("CREATE OR REPLACE TABLE orders AS SELECT * FROM source_df")
        schema = schema_from_duckdb(con, table_name="orders")
    finally:
        con.close()
    log_event(logger, "dataframe_converted_to_duckdb", rows=len(df), columns=len(df.columns), path=str(db_path))
    return DataSource(source_kind=source_kind, schema=schema, display_name=display_name, db_path=str(db_path), table_name="orders")


def prepare_uploaded_source(
    uploaded_file: Any,
    cache_dir: Path,
    logger: Any,
    sheet_name: str | int | None = None,
    table_name: str = "orders",
    ingest_method: str = "direct",
) -> DataSource:
    upload_dir = cache_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    name = Path(uploaded_file.name).name
    suffix = Path(name).suffix.lower()
    destination = upload_dir / name
    with destination.open("wb") as handle:
        handle.write(uploaded_file.getbuffer())
    if suffix == ".csv":
        if ingest_method == "sql":
            return prepare_csv_source(destination, cache_dir, logger=logger, force=True)
        return prepare_csv_memory_source(destination, logger)
    if suffix in {".xlsx", ".xls"}:
        source = prepare_excel_source(destination, sheet_name, logger)
        if ingest_method == "sql" and source.dataframe is not None:
            return dataframe_to_duckdb_source(source.dataframe, cache_dir, logger, destination.name, "Excel SQL cache")
        return source
    if suffix == ".pdf":
        source = prepare_pdf_source(destination, logger)
        if ingest_method == "sql" and source.dataframe is not None:
            return dataframe_to_duckdb_source(source.dataframe, cache_dir, logger, destination.name, "PDF SQL cache")
        return source
    if suffix in {".duckdb", ".db"}:
        return prepare_duckdb_source(destination, table_name, logger)
    if suffix == ".json":
        records = json.loads(destination.read_text(encoding="utf-8"))
        if isinstance(records, dict):
            records = records.get("data", records.get("records", []))
        if not isinstance(records, list) or not records:
            raise ValueError("Uploaded JSON must be a non-empty list or contain data/records.")
        df = coerce_date_columns(normalize_dataframe_columns(pd.DataFrame(records)))
        schema = schema_from_dataframe(df, source_name="Uploaded JSON")
        log_event(logger, "json_loaded_in_memory", rows=len(df), columns=len(df.columns), path=str(destination))
        if ingest_method == "sql":
            return dataframe_to_duckdb_source(df, cache_dir, logger, destination.name, "JSON SQL cache")
        return DataSource(source_kind="Uploaded JSON", schema=schema, display_name=destination.name, memory_key=f"json::{destination}", dataframe=df)
    raise ValueError("Unsupported upload type. Use CSV, XLSX, XLS, PDF, JSON, or DuckDB.")


def prepare_local_file_source(path: Path, cache_dir: Path, logger: Any, table_name: str, sheet_name: str | int | None, force: bool, ingest_method: str = "sql") -> DataSource:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        if ingest_method == "direct":
            return prepare_csv_memory_source(path, logger=logger)
        return prepare_csv_source(path, cache_dir, logger=logger, force=force)
    if suffix in {".xlsx", ".xls"}:
        source = prepare_excel_source(path, sheet_name, logger=logger)
        if ingest_method == "sql" and source.dataframe is not None:
            return dataframe_to_duckdb_source(source.dataframe, cache_dir, logger, path.name, "Excel SQL cache")
        return source
    if suffix == ".pdf":
        source = prepare_pdf_source(path, logger=logger)
        if ingest_method == "sql" and source.dataframe is not None:
            return dataframe_to_duckdb_source(source.dataframe, cache_dir, logger, path.name, "PDF SQL cache")
        return source
    if suffix in {".duckdb", ".db"}:
        return prepare_duckdb_source(path, table_name, logger=logger)
    if suffix == ".json":
        records = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(records, dict):
            records = records.get("data", records.get("records", []))
        if not isinstance(records, list) or not records:
            raise ValueError("JSON file must be a non-empty list or contain data/records.")
        df = coerce_date_columns(normalize_dataframe_columns(pd.DataFrame(records)))
        schema = schema_from_dataframe(df, source_name="Local JSON file")
        if ingest_method == "sql":
            return dataframe_to_duckdb_source(df, cache_dir, logger, path.name, "JSON SQL cache")
        return DataSource(source_kind="Local JSON", schema=schema, display_name=path.name, memory_key=f"local-json::{path}", dataframe=df)
    raise ValueError("Unsupported local file type. Use CSV, XLSX, XLS, PDF, JSON, or DuckDB.")


def parse_records_to_source(records: Any, cache_dir: Path, logger: Any, display_name: str, source_kind: str, ingest_method: str) -> DataSource:
    if isinstance(records, dict):
        records = records.get("data", records.get("records", []))
    if not isinstance(records, list) or not records:
        raise ValueError("Connector output must be a non-empty JSON list or contain data/records.")
    df = coerce_date_columns(normalize_dataframe_columns(pd.DataFrame(records)))
    if ingest_method == "sql":
        return dataframe_to_duckdb_source(df, cache_dir, logger, display_name, f"{source_kind} SQL cache")
    schema = schema_from_dataframe(df, source_name=source_kind)
    return DataSource(source_kind=source_kind, schema=schema, display_name=display_name, memory_key=f"{source_kind}::{display_name}", dataframe=df)
