from __future__ import annotations

import json
import re
import hashlib
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
    seen: dict[str, int] = {}
    columns: list[str] = []
    for index, column in enumerate(df.columns):
        name = normalize_identifier(str(column), index)
        count = seen.get(name, 0)
        seen[name] = count + 1
        if count:
            name = f"{name}_{count + 1}"
        columns.append(name)
    normalized = df.copy()
    normalized.columns = columns
    return normalized


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


_REPORT_ROW_RE = re.compile(r"^\s*(\d+)\s+(\d{2}/\d{2}/\d{4})\s*$")
_GSTIN_RE = re.compile(r"^\d{2}[A-Z0-9]{10}[A-Z0-9]Z[A-Z0-9]$", re.IGNORECASE)
_HSN_RE = re.compile(r"^\d{6,8}$")
_NUMBER_RE = re.compile(r"^-?\d[\d,]*(?:\.\d*)?$")
_MONTH_RE = re.compile(r"^[A-Za-z]+20\d{2}$")


def _normalize_report_month_name(name: str) -> str:
    if not name:
        return ""
    # If it's already spaced, return as is
    if " " in name:
        return name
    # If it matches MonthYear (e.g. January2026), insert space
    match = re.search(r"([A-Za-z]+)(20\d{2})", name)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return name


def _split_serial_date(value: str) -> tuple[str, str] | None:
    match = _REPORT_ROW_RE.match(value)
    if not match:
        return None
    return match.group(1), match.group(2)


def _parse_report_date(value: str) -> pd.Timestamp:
    return pd.to_datetime(value, format="%d/%m/%Y", errors="coerce")


def _is_report_number(value: str) -> bool:
    return bool(_NUMBER_RE.match(value.strip()))


def _split_report_tokens(value: str) -> list[str]:
    text = value.strip()
    if not text:
        return []
    parts = text.split()
    if len(parts) > 1 and all(_is_report_number(part) or _HSN_RE.match(part) or _MONTH_RE.match(part) for part in parts):
        return parts
    return [text]


def _extract_gstin(value: str) -> tuple[str, str, str]:
    match = _GSTIN_RE.search(value)
    if not match:
        return value.strip(), "", ""
    return value[:match.start()].strip(), match.group(0), value[match.end():].strip()


def _looks_supplier_part_code(value: str) -> bool:
    text = value.strip()
    return bool(text) and " " not in text and any(ch.isdigit() for ch in text) and len(text) >= 4


def _normalize_sales_book_middle(account: str, middle: list[str]) -> tuple[str, str, str, str]:
    account_prefix, account_gstin, account_suffix = _extract_gstin(account)
    normalized_account = account_prefix or account
    parts = ([account_gstin] if account_gstin else []) + ([account_suffix] if account_suffix else []) + middle

    gstin = ""
    content: list[str] = []
    for part in parts:
        before, found_gstin, after = _extract_gstin(part)
        if before:
            content.append(before)
        if found_gstin and not gstin:
            gstin = found_gstin
        if after:
            content.append(after)

    supplier_part_code = ""
    product_parts: list[str] = []
    for index, part in enumerate(content):
        if not supplier_part_code:
            first, _, rest = part.partition(" ")
            if _looks_supplier_part_code(first):
                supplier_part_code = first
                if rest.strip():
                    product_parts.append(rest.strip())
                continue
            if index == 0 and _looks_supplier_part_code(part):
                supplier_part_code = part
                continue
        product_parts.append(part)
    return normalized_account, gstin, supplier_part_code, " ".join(product_parts)


def _read_sales_order_blocks(doc: Any) -> pd.DataFrame | None:
    rows: list[dict[str, Any]] = []
    page_count = getattr(doc, "page_count", None)
    if page_count is None:
        page_count = len(doc)
    for page_index in range(int(page_count)):
        for block in doc[page_index].get_text("blocks"):
            text = str(block[4] if len(block) > 4 else "").strip()
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if len(lines) < 6:
                continue
            serial_date = _split_serial_date(lines[0])
            if not serial_date:
                continue
            serial_no, date = serial_date
            tail = lines[1:]
            if len(tail) < 5:
                continue
            rows.append({
                "s_no": serial_no,
                "date": _parse_report_date(date),
                "exchange_rate": tail[0],
                "vno": tail[1],
                "account": tail[2],
                "product": " ".join(tail[3:-2]),
                "quantity": tail[-2],
                "rate": tail[-1],
            })
    if len(rows) < 10:
        return None
    return pd.DataFrame(rows)


def _parse_sales_book_values(values: list[str]) -> tuple[list[str], dict[str, str]] | None:
    expanded: list[str] = []
    for value in values:
        expanded.extend(_split_report_tokens(value))
    if len(expanded) < 11:
        return None

    month_name = expanded[-1]
    cursor = len(expanded) - 2
    numeric_tail_reversed: list[str] = []
    while cursor >= 0:
        token = expanded[cursor]
        if not _is_report_number(token):
            break
        numeric_tail_reversed.append(token)
        cursor -= 1
    if len(numeric_tail_reversed) not in {8, 10}:
        return None
    numeric_tail = list(reversed(numeric_tail_reversed))
    if len(numeric_tail) == 10:
        fields = {
            "quantity": numeric_tail[0],
            "rate": numeric_tail[1],
            "net": numeric_tail[2],
            "hsn_code": numeric_tail[3],
            "gross": numeric_tail[4],
            "discount": numeric_tail[5],
            "cgst_rate": numeric_tail[6],
            "cgst": numeric_tail[7],
            "sgst_rate": numeric_tail[8],
            "sgst": numeric_tail[9],
            "igst_rate": "",
            "igst": "",
            "month_name": month_name,
        }
    else:
        fields = {
            "quantity": numeric_tail[0],
            "rate": numeric_tail[1],
            "net": numeric_tail[2],
            "hsn_code": numeric_tail[3],
            "gross": numeric_tail[4],
            "discount": numeric_tail[5],
            "cgst_rate": "",
            "cgst": "",
            "sgst_rate": "",
            "sgst": "",
            "igst_rate": numeric_tail[6],
            "igst": numeric_tail[7],
            "month_name": month_name,
        }
    return expanded[: cursor + 1], fields


def _read_sales_book_blocks(doc: Any) -> pd.DataFrame | None:
    rows: list[dict[str, Any]] = []
    page_count = getattr(doc, "page_count", None)
    if page_count is None:
        page_count = len(doc)
    for page_index in range(int(page_count)):
        for block in doc[page_index].get_text("blocks"):
            text = str(block[4] if len(block) > 4 else "").strip()
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if len(lines) < 10:
                continue
            serial_date = _split_serial_date(lines[0])
            if not serial_date:
                continue
            serial_no, date = serial_date
            tail = lines[1:]
            month_name = tail[-1]
            values = tail[:-1]
            if len(values) < 9:
                continue
            vno, account = values[0], values[1]
            parsed_values = _parse_sales_book_values(values[2:] + [month_name])
            if not parsed_values:
                continue
            middle, tax_fields = parsed_values
            account, gstin, supplier_part_code, product = _normalize_sales_book_middle(account, middle)
            if not product or _is_report_number(product):
                continue
            rows.append({
                "s_no": serial_no,
                "date": _parse_report_date(date),
                "vno": vno,
                "account": account,
                "gstin": gstin,
                "supplier_part_code": supplier_part_code,
                "product": product,
                **tax_fields,
            })
    if len(rows) < 10:
        return None
    return pd.DataFrame(rows)


def _read_known_report_blocks(doc: Any) -> pd.DataFrame | None:
    if int(getattr(doc, "page_count", len(doc) if hasattr(doc, "__len__") else 0)) <= 0:
        return None
    first_text = doc[0].get_text("text")
    if "Sales Orders Book Report" in first_text:
        return _read_sales_order_blocks(doc)
    if "Sales Book Report" in first_text:
        return _read_sales_book_blocks(doc)
    return None


def _read_pdf_tables_with_pymupdf(pdf_path: Path) -> pd.DataFrame:
    try:
        import pymupdf
    except Exception:
        import fitz as pymupdf

    frames: list[pd.DataFrame] = []
    doc = pymupdf.open(str(pdf_path))
    try:
        report_df = _read_known_report_blocks(doc)
        if report_df is not None and not report_df.empty:
            return report_df
        page_count = getattr(doc, "page_count", None)
        if page_count is None:
            page_count = len(doc)
        page_count = int(page_count)
        for page_index in range(page_count):
            page = doc[page_index]
            tables = page.find_tables(strategy="lines")
            for table in getattr(tables, "tables", []):
                df = _table_to_dataframe(table.extract())
                if df is not None and not df.empty:
                    frames.append(df)
    finally:
        close = getattr(doc, "close", None)
        if close:
            close()
    if not frames:
        raise ValueError("No tables found with PyMuPDF.")
    return pd.concat(frames, ignore_index=True, sort=False)


def _read_pdf_tables_with_pdfplumber(pdf_path: Path) -> pd.DataFrame:
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


def read_pdf_tables(pdf_path: Path) -> pd.DataFrame:
    try:
        return _read_pdf_tables_with_pymupdf(pdf_path)
    except Exception:
        return _read_pdf_tables_with_pdfplumber(pdf_path)


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


def _safe_table_name(sheet_name: str, seen: dict[str, int]) -> str:
    base = re.sub(r"[^0-9A-Za-z]+", "_", sheet_name.strip()).strip("_").lower() or "sheet"
    if base[0].isdigit():
        base = f"t_{base}"
    count = seen.get(base, 0) + 1
    seen[base] = count
    return base if count == 1 else f"{base}_{count}"


def prepare_excel_workbook_duckdb_sources(
    excel_path: Path,
    sheet_names: list[str],
    cache_dir: Path,
    logger: Any,
) -> list[DataSource]:
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_path}")
    selected = [str(sheet).strip() for sheet in sheet_names if str(sheet).strip()]
    if not selected:
        raise ValueError("Select at least one sheet")

    available = list(pd.ExcelFile(excel_path).sheet_names)
    missing = [sheet for sheet in selected if sheet not in available]
    if missing:
        raise ValueError(f"Sheet not found: {', '.join(missing)}")

    sql_dir = cache_dir / "sql_sources"
    sql_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^0-9A-Za-z_-]+", "_", excel_path.stem).strip("_") or "workbook"
    digest = hashlib.sha256(
        f"{excel_path.resolve()}::{excel_path.stat().st_mtime_ns}::{json.dumps(selected)}".encode("utf-8")
    ).hexdigest()[:12]
    db_path = sql_dir / f"{safe_stem}_{digest}.duckdb"
    if db_path.exists():
        db_path.unlink()

    import duckdb

    seen: dict[str, int] = {}
    sources: list[DataSource] = []
    con = duckdb.connect(str(db_path))
    try:
        for sheet in selected:
            if excel_path.suffix.lower() == ".xlsx":
                df = _read_xlsx_via_duckdb(excel_path, sheet)
            else:
                df = pd.read_excel(excel_path, sheet_name=sheet)
            df = coerce_date_columns(normalize_dataframe_columns(df))
            table_name = _safe_table_name(sheet, seen)
            con.register("sheet_df", df)
            con.execute(f'CREATE OR REPLACE TABLE "{table_name}" AS SELECT * FROM sheet_df')
            con.unregister("sheet_df")
            schema = schema_from_duckdb(con, table_name=table_name)
            sources.append(
                DataSource(
                    source_kind="Excel workbook table",
                    schema=schema,
                    display_name=f"{excel_path.name} - {sheet}",
                    db_path=str(db_path),
                    table_name=table_name,
                )
            )
    finally:
        con.close()
    if logger:
        log_event(logger, "excel_workbook_converted_to_duckdb", sheets=len(sources), path=str(excel_path), db_path=str(db_path))
    return sources


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
