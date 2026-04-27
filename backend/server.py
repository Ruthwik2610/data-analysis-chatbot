from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import logging
import math
import os
import shutil
import socket
import sys
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config import AppConfig
from src.data_sources import (
    DataSource,
    dataframe_to_duckdb_source,
    prepare_api_source,
    prepare_csv_memory_source,
    prepare_csv_source,
    prepare_duckdb_source,
    prepare_excel_source,
    prepare_local_file_source,
)
from src.logging_config import log_event, setup_loggers
from src.mcp_pool import extract_text_content, get_pool, parse_tool_result_to_dataframe
from src.model_router import GeminiRouter, LLMUnavailable, ModelChoice
from src.query_engine import (
    build_query_plan,
    build_total_plan,
    heuristic_intent,
    validate_readonly_sql,
    wants_grand_total,
)
from src.utils import conversation_summary, params_key
from src.visualization import choose_visualization, deterministic_summary

from backend.storage import Storage


CONFIG = AppConfig.from_env()
LOGGERS = setup_loggers(REPO_ROOT / "logs")
DB = Storage(CONFIG.cache_dir / "app.sqlite")
SOURCES: dict[str, DataSource] = {}
UPLOAD_DIR = CONFIG.cache_dir / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PENDING: dict[str, dict[str, Any]] = {}  # upload_id -> { path, kind, file_name, ... }

API_KEY = os.getenv("API_KEY", "").strip()
ALLOWED_ORIGINS = [o.strip() for o in os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",") if o.strip()]
ALLOW_PRIVATE_API_URLS = os.getenv("ALLOW_PRIVATE_API_URLS", "0") == "1"

if not API_KEY:
    logging.warning(
        "API_KEY is not set — the API is unauthenticated. Set API_KEY before exposing this server.",
    )

# Singleton — re-creating per request reloads the genai client and wastes time.
ROUTER = GeminiRouter(
    api_key=CONFIG.gemini_api_key,
    models=ModelChoice(CONFIG.default_model, CONFIG.escalation_model, CONFIG.fallback_model),
    logger=LOGGERS["llm"],
    char_budget=CONFIG.prompt_char_budget,
)


PUBLIC_PATHS = {"/health"}


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-load saved MCP bridges (mcp.json) into the pool, then start the
    # background health-check loop. Both happen on the FastAPI event loop.
    pool = get_pool()
    try:
        await pool.auto_load(REPO_ROOT / "mcp.json")
    except Exception as exc:
        logging.warning("MCP auto-load failed: %s", exc)
    pool.start_health_loop()
    try:
        yield
    finally:
        await pool.shutdown()


app = FastAPI(title="CSV Intelligence API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    # CORS preflight is handled by CORSMiddleware before this runs.
    if not API_KEY or request.url.path in PUBLIC_PATHS:
        return await call_next(request)
    if request.headers.get("authorization") != f"Bearer {API_KEY}":
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
    return await call_next(request)


def _make_id(prefix: str = "src") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _assert_public_url(url: str) -> None:
    """Block SSRF: reject URLs whose host resolves to a private/loopback/link-local
    address or the cloud metadata endpoint. Bypass with ALLOW_PRIVATE_API_URLS=1."""
    if ALLOW_PRIVATE_API_URLS:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="URL must be http or https")
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail="URL is missing a host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail=f"Could not resolve host: {host}")
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise HTTPException(
                status_code=400,
                detail=f"Refusing to fetch private/internal address {addr} (set ALLOW_PRIVATE_API_URLS=1 to override)",
            )
        if str(ip) == "169.254.169.254":
            raise HTTPException(status_code=400, detail="Refusing to fetch cloud metadata endpoint")


def _persist_source(source_id: str, source: DataSource, kind: str, origin: dict[str, Any] | None) -> dict[str, Any]:
    SOURCES[source_id] = source
    DB.upsert_source(
        source_id=source_id,
        name=source.display_name,
        kind=kind,
        rows=source.row_count,
        schema_json=json.dumps(source.schema, default=str),
        origin=origin,
    )
    DB.set_active_source(source_id)
    return _serialize_source(source_id, source, kind, active=True)


async def _rehydrate_source(row: dict[str, Any]) -> DataSource:
    """Rebuild a DataSource from its persisted origin record after server restart."""
    origin_str = row.get("origin")
    if not origin_str:
        raise HTTPException(status_code=410, detail=f"Source '{row['name']}' has no saved origin — re-attach it.")
    try:
        origin = json.loads(origin_str)
    except Exception:
        raise HTTPException(status_code=410, detail=f"Source '{row['name']}' has corrupted origin — re-attach it.")

    cache_logger = LOGGERS["cache"]
    cache_dir = CONFIG.cache_dir
    typ = origin.get("type")

    try:
        if typ == "csv_memory":
            return await asyncio.to_thread(prepare_csv_memory_source, Path(origin["path"]), cache_logger)
        if typ == "csv_sql":
            return await asyncio.to_thread(prepare_csv_source, Path(origin["path"]), cache_dir, cache_logger, False)
        if typ == "excel":
            return await asyncio.to_thread(prepare_excel_source, Path(origin["path"]), origin.get("sheet"), cache_logger)
        if typ == "duckdb":
            return await asyncio.to_thread(prepare_duckdb_source, Path(origin["path"]), origin.get("table", "orders"), cache_logger)
        if typ == "json":
            return await asyncio.to_thread(prepare_local_file_source, Path(origin["path"]), cache_dir, cache_logger, "orders", None, False, "direct")
        if typ == "api":
            _assert_public_url(origin["url"])
            return await asyncio.to_thread(prepare_api_source, origin["url"], cache_logger, origin.get("auth"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=410, detail=f"Source file no longer exists: {exc}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not rehydrate source: {exc}")

    raise HTTPException(status_code=400, detail=f"Cannot rehydrate source of unknown type '{typ}'")


def _serialize_source(source_id: str, source: DataSource, kind: str, active: bool) -> dict[str, Any]:
    return {
        "id": source_id,
        "name": source.display_name,
        "kind": kind,
        "rows": source.row_count,
        "columns": [c["name"] for c in source.schema.get("columns", [])],
        "active": active,
    }


# -- models ----------------------------------------------------------------
class AttachCSVPath(BaseModel):
    path: str
    sql_cache: bool = False


class AttachExcelPath(BaseModel):
    path: str
    sheet: str | None = None
    ingest: str = "direct"


class AttachDuckDB(BaseModel):
    path: str
    table: str = "orders"


class AttachAPI(BaseModel):
    url: str
    auth: str | None = None
    ingest: str = "direct"
    save_connector: bool = False


class CreateConnector(BaseModel):
    kind: str
    label: str
    config: dict[str, Any]


class MCPConnect(BaseModel):
    name: str | None = None
    url: str


class MCPUpdate(BaseModel):
    name: str | None = None
    url: str | None = None


class QueryRequest(BaseModel):
    chat_id: str | None = None
    question: str


# -- health ----------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# -- sources ---------------------------------------------------------------
@app.get("/sources")
def list_sources() -> list[dict[str, Any]]:
    rows = DB.list_sources()
    out = []
    for row in rows:
        out.append({
            "id": row["id"],
            "name": row["name"],
            "kind": row["kind"],
            "rows": row["rows"],
            "active": bool(row["active"]),
            "loaded": row["id"] in SOURCES,
        })
    return out


@app.post("/sources/csv")
def attach_csv(body: AttachCSVPath) -> dict[str, Any]:
    try:
        path = Path(body.path).expanduser()
        if body.sql_cache:
            source = prepare_csv_source(path, CONFIG.cache_dir, logger=LOGGERS["cache"], force=False)
            origin = {"type": "csv_sql", "path": str(path)}
        else:
            source = prepare_csv_memory_source(path, logger=LOGGERS["cache"])
            origin = {"type": "csv_memory", "path": str(path)}
        source_id = _make_id()
        return _persist_source(source_id, source, "csv", origin)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/sources/excel")
def attach_excel(body: AttachExcelPath) -> dict[str, Any]:
    try:
        path = Path(body.path).expanduser()
        source = prepare_excel_source(path, body.sheet, LOGGERS["cache"])
        if body.ingest == "sql" and source.dataframe is not None:
            source = dataframe_to_duckdb_source(source.dataframe, CONFIG.cache_dir, LOGGERS["cache"], path.name, "Excel SQL cache")
        origin = {"type": "excel", "path": str(path), "sheet": body.sheet, "ingest": body.ingest}
        source_id = _make_id()
        return _persist_source(source_id, source, "xlsx", origin)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/sources/duckdb")
def attach_duckdb(body: AttachDuckDB) -> dict[str, Any]:
    try:
        path = Path(body.path).expanduser()
        source = prepare_duckdb_source(path, body.table, logger=LOGGERS["cache"])
        origin = {"type": "duckdb", "path": str(path), "table": body.table}
        source_id = _make_id()
        return _persist_source(source_id, source, "duckdb", origin)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/sources/api")
def attach_api(body: AttachAPI) -> dict[str, Any]:
    _assert_public_url(body.url)
    try:
        source = prepare_api_source(body.url, LOGGERS["cache"], auth_header=body.auth)
        if body.ingest == "sql" and source.dataframe is not None:
            source = dataframe_to_duckdb_source(source.dataframe, CONFIG.cache_dir, LOGGERS["cache"], body.url, "API SQL cache")
        origin = {"type": "api", "url": body.url, "auth": body.auth, "ingest": body.ingest}
        source_id = _make_id()
        result = _persist_source(source_id, source, "api", origin)
        if body.save_connector:
            DB.add_connector(kind="api", label=body.url, config={"url": body.url, "auth": body.auth})
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _list_excel_sheets(path: Path) -> list[str]:
    return list(pd.ExcelFile(path).sheet_names)


def _list_duckdb_tables(path: Path) -> list[str]:
    import duckdb

    con = duckdb.connect(str(path), read_only=True)
    try:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name"
        ).fetchall()
    finally:
        con.close()
    return [r[0] for r in rows]


def _save_upload_sync(file_obj: Any, dest: Path) -> None:
    with dest.open("wb") as out:
        shutil.copyfileobj(file_obj, out)


@app.post("/sources/upload")
async def upload_source(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")
    upload_id = uuid.uuid4().hex[:10]
    upload_dir = UPLOAD_DIR / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / file.filename
    # Stream the upload to disk on a worker thread so the event loop stays responsive.
    await asyncio.to_thread(_save_upload_sync, file.file, dest)

    suffix = dest.suffix.lower()
    file_name = file.filename
    size_mb = round(dest.stat().st_size / (1024 * 1024), 1)

    try:
        if suffix in {".xlsx", ".xls"}:
            sheets = await asyncio.to_thread(_list_excel_sheets, dest)
            if len(sheets) > 1:
                PENDING[upload_id] = {"path": str(dest), "file_name": file_name, "sheets": sheets, "kind": "xlsx"}
                return {"pending": {
                    "kind": "sheet_pick",
                    "upload_id": upload_id,
                    "file_name": file_name,
                    "sheets": sheets,
                }}
            sheet = sheets[0] if sheets else None
            source = await asyncio.to_thread(prepare_excel_source, dest, sheet, LOGGERS["cache"])
            origin = {"type": "excel", "path": str(dest), "sheet": sheet, "ingest": "direct"}
            return _persist_source(_make_id(), source, "xlsx", origin)

        if suffix in {".duckdb", ".db"}:
            tables = await asyncio.to_thread(_list_duckdb_tables, dest)
            if len(tables) > 1:
                PENDING[upload_id] = {"path": str(dest), "file_name": file_name, "tables": tables, "kind": "duckdb"}
                return {"pending": {
                    "kind": "table_pick",
                    "upload_id": upload_id,
                    "file_name": file_name,
                    "tables": tables,
                }}
            table = tables[0] if tables else "orders"
            source = await asyncio.to_thread(prepare_duckdb_source, dest, table, LOGGERS["cache"])
            origin = {"type": "duckdb", "path": str(dest), "table": table}
            return _persist_source(_make_id(), source, "duckdb", origin)

        if suffix == ".csv":
            if size_mb > 100:
                PENDING[upload_id] = {"path": str(dest), "file_name": file_name, "size_mb": size_mb, "kind": "csv"}
                return {"pending": {
                    "kind": "ingest_pick",
                    "upload_id": upload_id,
                    "file_name": file_name,
                    "size_mb": size_mb,
                }}
            source = await asyncio.to_thread(prepare_csv_memory_source, dest, LOGGERS["cache"])
            origin = {"type": "csv_memory", "path": str(dest)}
            return _persist_source(_make_id(), source, "csv", origin)

        if suffix == ".json":
            from src.data_sources import prepare_local_file_source

            source = await asyncio.to_thread(
                prepare_local_file_source,
                dest, CONFIG.cache_dir, LOGGERS["cache"], "orders", None, False, "direct",
            )
            origin = {"type": "json", "path": str(dest)}
            return _persist_source(_make_id(), source, "json", origin)

        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class ResolvePending(BaseModel):
    upload_id: str
    value: str  # sheet name, table name, or "direct" / "sql"


@app.post("/sources/resolve_pending")
def resolve_pending(body: ResolvePending) -> dict[str, Any]:
    record = PENDING.get(body.upload_id)
    if not record:
        raise HTTPException(status_code=404, detail="Pending upload not found or already resolved")
    path = Path(record["path"])
    try:
        if record["kind"] == "xlsx":
            source = prepare_excel_source(path, body.value, LOGGERS["cache"])
            origin = {"type": "excel", "path": str(path), "sheet": body.value, "ingest": "direct"}
            result = _persist_source(_make_id(), source, "xlsx", origin)
        elif record["kind"] == "duckdb":
            source = prepare_duckdb_source(path, body.value, logger=LOGGERS["cache"])
            origin = {"type": "duckdb", "path": str(path), "table": body.value}
            result = _persist_source(_make_id(), source, "duckdb", origin)
        elif record["kind"] == "csv":
            ingest = body.value if body.value in ("direct", "sql") else "direct"
            if ingest == "sql":
                source = prepare_csv_source(path, CONFIG.cache_dir, logger=LOGGERS["cache"], force=False)
            else:
                source = prepare_csv_memory_source(path, logger=LOGGERS["cache"])
            origin = {"type": f"csv_{ingest}", "path": str(path)}
            result = _persist_source(_make_id(), source, "csv", origin)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown pending kind: {record['kind']}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    PENDING.pop(body.upload_id, None)
    return result


@app.delete("/sources/{source_id}")
def delete_source(source_id: str) -> dict[str, Any]:
    DB.delete_source(source_id)
    SOURCES.pop(source_id, None)
    return {"ok": True}


@app.post("/sources/{source_id}/activate")
def activate_source(source_id: str) -> dict[str, Any]:
    DB.set_active_source(source_id)
    return {"ok": True}


# -- chats -----------------------------------------------------------------
@app.get("/chats")
def list_chats() -> list[dict[str, Any]]:
    return DB.list_chats()


@app.get("/chats/{chat_id}")
def get_chat(chat_id: str) -> dict[str, Any]:
    chat = DB.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@app.post("/chats")
def create_chat() -> dict[str, Any]:
    return DB.create_chat()


@app.delete("/chats/{chat_id}")
def delete_chat(chat_id: str) -> dict[str, Any]:
    DB.delete_chat(chat_id)
    return {"ok": True}


# -- connectors ------------------------------------------------------------
@app.get("/connectors")
def list_connectors() -> list[dict[str, Any]]:
    return DB.list_connectors()


@app.delete("/connectors/{connector_id}")
def delete_connector(connector_id: str) -> dict[str, Any]:
    DB.delete_connector(connector_id)
    return {"ok": True}


# ---- MCP pool (persistent bridge connections, agent-loop chat) ----------
@app.get("/mcp/connectors")
def list_mcp_connectors() -> list[dict[str, Any]]:
    return get_pool().list_status()


@app.post("/mcp/connectors")
async def add_mcp_connector(body: MCPConnect) -> dict[str, Any]:
    if not body.url.strip():
        raise HTTPException(status_code=400, detail="url is required")
    cid = await get_pool().connect(body.url.strip(), body.name or body.url.strip())
    state = get_pool().connectors.get(cid)
    if state and state.status == "error":
        raise HTTPException(status_code=400, detail=state.last_error or "Failed to connect to MCP bridge")
    return {
        "id": cid,
        "name": state.name if state else body.name,
        "url": body.url,
        "status": state.status if state else "error",
        "tools": state.tools if state and state.status == "connected" else [],
    }


@app.put("/mcp/connectors/{connector_id}")
async def update_mcp_connector(connector_id: str, body: MCPUpdate) -> dict[str, Any]:
    pool = get_pool()
    state = pool.connectors.get(connector_id)
    if not state:
        raise HTTPException(status_code=404, detail="Connector not found")
    if body.url and body.url.strip() and body.url.strip() != state.url:
        await pool.connect(body.url.strip(), body.name or state.name, connector_id=connector_id)
        state = pool.connectors[connector_id]
        if state.status == "error":
            raise HTTPException(status_code=400, detail=state.last_error or "Reconnect failed")
    elif body.name:
        await pool.rename(connector_id, body.name)
    state = pool.connectors[connector_id]
    return {"id": state.id, "name": state.name, "url": state.url, "status": state.status, "tools": state.tools}


@app.delete("/mcp/connectors/{connector_id}")
async def remove_mcp_connector(connector_id: str) -> dict[str, Any]:
    ok = await get_pool().disconnect(connector_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Connector not found")
    return {"ok": True}


@app.post("/connectors/{connector_id}/use")
async def use_connector(connector_id: str) -> dict[str, Any]:
    record = DB.get_connector(connector_id)
    if not record:
        raise HTTPException(status_code=404, detail="Connector not found")
    cfg = record["config"]
    try:
        if record["kind"] == "api":
            _assert_public_url(cfg["url"])
            source = prepare_api_source(cfg["url"], LOGGERS["cache"], auth_header=cfg.get("auth"))
            origin = {"type": "api", "url": cfg["url"], "auth": cfg.get("auth"), "ingest": "direct"}
            source_id = _make_id()
            return _persist_source(source_id, source, "api", origin)
        raise HTTPException(status_code=400, detail=f"Unknown connector kind: {record['kind']}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# -- query (SSE) -----------------------------------------------------------
def _df_to_payload(df: pd.DataFrame, limit: int = 200) -> dict[str, Any]:
    head = df.head(limit)
    rows: list[list[Any]] = []
    for _, row in head.iterrows():
        cleaned: list[Any] = []
        for v in row.tolist():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                cleaned.append(None)
            elif hasattr(v, "isoformat"):
                cleaned.append(v.isoformat())
            else:
                cleaned.append(v)
        rows.append(cleaned)
    return {
        "columns": [str(c) for c in df.columns],
        "rows": rows,
        "row_count": int(len(df)),
        "truncated": len(df) > limit,
    }


def _format_period_for_llm(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    ts = pd.Timestamp(value)
    # Month-grain (start of month, midnight) → "Apr 2023"
    if ts.day == 1 and ts.hour == 0 and ts.minute == 0 and ts.second == 0:
        return ts.strftime("%b %Y")
    # Day-grain → "Apr 15, 2023"
    if ts.hour == 0 and ts.minute == 0 and ts.second == 0:
        return ts.strftime("%b %d, %Y")
    # Otherwise full timestamp
    return ts.strftime("%b %d, %Y %H:%M")


def _run_query(plan, source: DataSource) -> tuple[pd.DataFrame, int]:
    import duckdb

    start = time.perf_counter()
    p_key = params_key(plan.params)
    if source.db_path:
        params = json.loads(p_key)
        con = duckdb.connect(source.db_path, read_only=True)
        try:
            if source.table_name != "orders":
                safe_table = '"' + source.table_name.replace('"', '""') + '"'
                con.execute(f"CREATE TEMP VIEW orders AS SELECT * FROM {safe_table}")
            df = con.execute(plan.sql, params).fetchdf()
        finally:
            con.close()
    elif source.dataframe is not None:
        params = json.loads(p_key)
        con = duckdb.connect(":memory:")
        try:
            con.register("orders", source.dataframe)
            df = con.execute(plan.sql, params).fetchdf()
        finally:
            con.close()
    else:
        raise RuntimeError("No executable source")
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return df, elapsed_ms


def _build_mcp_summary(pool) -> str:
    """Compact text describing connected MCP bridges and their tools, for the
    intent classifier to decide whether to route a question to MCP."""
    lines: list[str] = []
    for s in pool.connectors.values():
        if s.status != "connected" or not s.tools:
            continue
        lines.append(f"### {s.name}")
        for t in s.tools:
            desc = (t.get("description") or "").strip().splitlines()[0] if t.get("description") else ""
            if len(desc) > 140:
                desc = desc[:140] + "…"
            lines.append(f"  - {t['name']}: {desc}" if desc else f"  - {t['name']}")
    return "\n".join(lines)


async def _run_mcp_agent(
    chat_id: str,
    question: str,
    history: list[dict[str, Any]],
    request_id: str,
) -> AsyncIterator[dict[str, Any]]:
    """Drive the function-calling agent loop, stream SSE events, and persist the
    final assistant message. Picks the largest tabular tool result (>=2 rows,
    >=2 cols) and emits it as a `result` event so ResultBlock renders a chart."""
    pool = get_pool()
    specs, routing = pool.aggregate_tools()
    if not specs:
        msg_text = "I don't have any tools available right now — connect an MCP bridge and try again."
        msg = DB.add_message(chat_id, "assistant", msg_text, payload={"kind": "error"})
        yield {"event": "text", "data": json.dumps({"delta": msg_text})}
        yield {"event": "done", "data": json.dumps({"message_id": msg["id"], "chat_id": chat_id})}
        return

    connector_summary_lines: list[str] = []
    by_connector: dict[str, list[str]] = {}
    name_lookup: dict[str, str] = {}
    for s in pool.connectors.values():
        if s.status == "connected":
            name_lookup[s.id] = s.name
            by_connector.setdefault(s.id, []).extend(t["name"] for t in s.tools)
    for cid, tnames in by_connector.items():
        connector_summary_lines.append(f"### {name_lookup[cid]} · {len(tnames)} tools\n  - " + "\n  - ".join(tnames))
    connector_summary = "\n\n".join(connector_summary_lines)

    # Track per-tool results so we can pick the largest tabular one for charting.
    collected_dfs: list[tuple[str, pd.DataFrame]] = []

    async def on_tool_call(tool_name: str, args: dict[str, Any]):
        connector_id = routing.get(tool_name)
        if not connector_id:
            return "", f"Tool '{tool_name}' is not available.", None
        try:
            result = await pool.call_tool(connector_id, tool_name, args)
            text = extract_text_content(result)
            df = parse_tool_result_to_dataframe(text)
            if df is not None:
                collected_dfs.append((tool_name, df))
            # Truncate text fed back to LLM to keep context lean (DMV uses 6000).
            if len(text) > 6000:
                text = text[:6000] + f"\n\n[truncated at 6000 of {len(text)} chars]"
            return text, None, connector_id
        except Exception as exc:
            return "", str(exc), connector_id

    full_text_parts: list[str] = []
    last_tool_call: dict[str, Any] | None = None

    try:
        async for ev in ROUTER.agent_loop_stream(
            request_id=request_id,
            user_question=question,
            conversation_summary=conversation_summary(history),
            tool_specs=specs,
            connector_summary=connector_summary,
            on_tool_call=on_tool_call,
        ):
            kind = ev["kind"]
            if kind == "tool_call":
                last_tool_call = ev
                connector_id = routing.get(ev["name"])
                cname = name_lookup.get(connector_id, "MCP")
                args_str = ", ".join(f"{k}={v!r}" for k, v in (ev.get("args") or {}).items())
                step = f"Calling {ev['name']}({args_str}) on {cname}"
                yield {"event": "thinking", "data": json.dumps({"step": step})}
            elif kind == "tool_result":
                if ev.get("error"):
                    yield {"event": "thinking", "data": json.dumps({"step": f"{ev['name']} returned an error"})}
                else:
                    yield {"event": "thinking", "data": json.dumps({"step": f"{ev['name']} returned data"})}
            elif kind == "text":
                delta = ev.get("delta") or ""
                full_text_parts.append(delta)
                yield {"event": "text", "data": json.dumps({"delta": delta})}
    except LLMUnavailable as exc:
        err_text = "All language models are unavailable right now. Try again in a moment."
        msg = DB.add_message(chat_id, "assistant", err_text, payload={"kind": "error", "detail": str(exc)})
        yield {"event": "error", "data": json.dumps({"message": err_text, "detail": str(exc)})}
        yield {"event": "done", "data": json.dumps({"message_id": msg["id"], "chat_id": chat_id})}
        return

    full_text = "".join(full_text_parts).strip() or "(no answer)"

    # Pick the largest tabular result for charting; emit a `result` event so the
    # frontend's existing ResultBlock can render it.
    result_payload: dict[str, Any] | None = None
    if collected_dfs:
        tool_name, df = max(collected_dfs, key=lambda p: len(p[1]))
        viz = "table" if len(df) > 25 else "bar"
        connector_id = routing.get(tool_name)
        cname = name_lookup.get(connector_id, "MCP")
        result_payload = {
            "title": tool_name,
            "viz": viz,
            "elapsed_ms": 0,
            "sql": "",
            "how": f"Source: {cname} via tool {tool_name}.",
            **_df_to_payload(df),
        }
        yield {"event": "result", "data": json.dumps(result_payload, default=str)}

    assistant_payload: dict[str, Any] = {"kind": "result" if result_payload else "text", "model": "agent"}
    if result_payload:
        assistant_payload["result"] = result_payload
    msg = DB.add_message(chat_id, "assistant", full_text, payload=assistant_payload)
    yield {"event": "done", "data": json.dumps({"message_id": msg["id"], "chat_id": chat_id})}


def _load_history(chat_id: str | None) -> list[dict[str, Any]]:
    if not chat_id:
        return []
    chat = DB.get_chat(chat_id)
    if not chat:
        return []
    return [{"role": m["role"], "content": m["content"]} for m in chat["messages"]]


@app.post("/query")
async def query(body: QueryRequest):
    chat_id = body.chat_id or DB.create_chat()["id"]
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    active_row = DB.get_active_source()
    pool = get_pool()
    has_mcp = any(s.status == "connected" for s in pool.connectors.values())

    if not active_row and not has_mcp:
        raise HTTPException(status_code=400, detail="Attach a source first")

    source: DataSource | None = None
    if active_row:
        source = SOURCES.get(active_row["id"])
        if source is None:
            # Server probably restarted — rebuild from saved origin.
            source = await _rehydrate_source(active_row)
            SOURCES[active_row["id"]] = source

    DB.add_message(chat_id, "user", question)
    chat = DB.get_chat(chat_id)
    if chat and (not chat.get("title") or chat["title"] == "New chat"):
        DB.update_chat_title(chat_id, question[:60])

    history = _load_history(chat_id)
    request_id = uuid.uuid4().hex[:12]

    async def event_stream() -> AsyncIterator[dict[str, Any]]:
        loop = asyncio.get_running_loop()

        if source is not None and active_row is not None:
            meta_source = {
                "id": active_row["id"],
                "name": active_row["name"],
                "kind": active_row["kind"],
                "rows": active_row["rows"],
            }
        else:
            connected = [s for s in pool.connectors.values() if s.status == "connected"]
            meta_source = {
                "id": None,
                "name": ", ".join(s.name for s in connected) or "MCP",
                "kind": "mcp",
                "rows": 0,
            }
        yield {
            "event": "meta",
            "data": json.dumps({"chat_id": chat_id, "source": meta_source}),
        }
        yield {"event": "thinking", "data": json.dumps({"step": "Reading your question"})}

        notices: list[dict[str, str]] = []

        def collect_fallback(from_model: str, to_model: str, reason: str) -> None:
            if not any(n["to"] == to_model for n in notices):
                notices.append({"from": from_model, "to": to_model, "reason": reason})

        if source is None:
            async for ev in _run_mcp_agent(chat_id, question, history, request_id):
                yield ev
            return

        try:
            mcp_summary_text = _build_mcp_summary(pool) if has_mcp else ""
            if ROUTER.available:
                intent, model_used = await loop.run_in_executor(
                    None,
                    lambda: ROUTER.classify_intent(
                        request_id=request_id,
                        user_question=question,
                        schema_context=source.schema,
                        conversation_summary=conversation_summary(history),
                        on_fallback=collect_fallback,
                        mcp_summary=mcp_summary_text,
                        local_source_name=active_row["name"],
                    ),
                )
            else:
                intent, model_used = heuristic_intent(question, source.allowed_columns), "offline-heuristic"

            route = (intent.get("route") or "local").lower()

            # Explicit MCP route — classifier decided the question belongs to a connected MCP source.
            if route == "mcp" and has_mcp:
                async for ev in _run_mcp_agent(chat_id, question, history, request_id):
                    yield ev
                return

            if intent.get("intent_type") == "clarification":
                content = intent.get("clarifying_question") or "Can you clarify the metric or grouping?"
                msg = DB.add_message(chat_id, "assistant", content, payload={"kind": "clarification", "model": model_used})
                yield {"event": "clarify", "data": json.dumps({"content": content, "message_id": msg["id"]})}
                yield {"event": "done", "data": json.dumps({"message_id": msg["id"]})}
                return

            if intent.get("intent_type") == "unsupported":
                # Safety net: if the classifier missed the route field but MCP is connected,
                # let the agent try (e.g. user asked about BigQuery while a CSV is active).
                if has_mcp:
                    async for ev in _run_mcp_agent(chat_id, question, history, request_id):
                        yield ev
                    return
                content = (
                    intent.get("clarifying_question")
                    or f"I can only answer questions about the loaded source ({active_row['name']}). Try asking about its columns, totals, breakdowns, or trends."
                )
                msg = DB.add_message(chat_id, "assistant", content, payload={"kind": "unsupported", "model": model_used})
                yield {"event": "clarify", "data": json.dumps({"content": content, "message_id": msg["id"]})}
                yield {"event": "done", "data": json.dumps({"message_id": msg["id"], "chat_id": chat_id})}
                return

            yield {"event": "thinking", "data": json.dumps({"step": f"Searching {active_row['name']}"})}

            plan = build_query_plan(intent, question, source.allowed_columns)
            validate_readonly_sql(plan.sql)

            df, elapsed_ms = await loop.run_in_executor(None, lambda: _run_query(plan, source))
            log_event(LOGGERS["query"], "query_executed", request_id=request_id, source=source.source_kind, sql_hash=plan.cache_key, rows=len(df), elapsed_ms=elapsed_ms)
            viz = choose_visualization(question, intent, df)

            result_payload = {
                "title": plan.title,
                "viz": viz,
                "elapsed_ms": elapsed_ms,
                "sql": plan.sql,
                "how": f"Source: {source.source_kind}. Model: {model_used}. {plan.how} Display: {viz}.",
                **_df_to_payload(df),
            }
            yield {"event": "result", "data": json.dumps(result_payload, default=str)}
            yield {"event": "thinking", "data": json.dumps({"step": "Putting an answer together"})}

            # Format datetime columns to human-readable labels before serializing to the LLM,
            # so the model doesn't parrot back ISO strings like "2023-04-01T00:00:00".
            sample_df = df.head(50).copy()
            for col in sample_df.columns:
                if pd.api.types.is_datetime64_any_dtype(sample_df[col]):
                    sample_df[col] = sample_df[col].apply(_format_period_for_llm)
            sample = sample_df.to_dict(orient="records")
            full_text_parts: list[str] = []

            # Always compute the grand total for multi-row breakdowns so the answer can quote it
            # without summing the (possibly truncated) sample. ~50ms extra DuckDB query.
            total_row: dict[str, Any] | None = None
            if (
                intent.get("intent_type") in {"aggregate", "trend", "comparison", "chart_request"}
                and (intent.get("dimensions") or len(df) > 1)
            ):
                try:
                    total_plan = build_total_plan(intent, source.allowed_columns)
                    validate_readonly_sql(total_plan.sql)
                    total_df, total_ms = await loop.run_in_executor(None, lambda: _run_query(total_plan, source))
                    if not total_df.empty:
                        raw = total_df.iloc[0].to_dict()
                        total_row = {}
                        for k, v in raw.items():
                            if hasattr(v, "item"):
                                v = v.item()
                            if isinstance(v, pd.Timestamp) or pd.api.types.is_datetime64_any_dtype(type(v)):
                                v = _format_period_for_llm(v)
                            total_row[k] = v
                        log_event(LOGGERS["query"], "grand_total_executed", request_id=request_id, sql_hash=total_plan.cache_key, elapsed_ms=total_ms)
                except Exception as exc:  # pragma: no cover - secondary query best-effort
                    log_event(LOGGERS["query"], "grand_total_failed", request_id=request_id, error=str(exc))

            if ROUTER.available:
                try:
                    chunks_iter = ROUTER.summarize_answer_stream(
                        request_id=request_id,
                        user_question=question,
                        intent=intent,
                        result_sample=sample,
                        row_count=len(df),
                        sql=plan.sql,
                        total_row=total_row,
                        on_fallback=collect_fallback,
                    )
                    while True:
                        chunk = await loop.run_in_executor(None, lambda it=chunks_iter: next(it, None))
                        if chunk is None:
                            break
                        full_text_parts.append(chunk)
                        yield {"event": "text", "data": json.dumps({"delta": chunk})}
                except LLMUnavailable as exc:
                    text = deterministic_summary(question, df, len(df))
                    full_text_parts = [text]
                    yield {"event": "text", "data": json.dumps({"delta": text})}
            else:
                text = deterministic_summary(question, df, len(df))
                full_text_parts = [text]
                yield {"event": "text", "data": json.dumps({"delta": text})}

            full_text = "".join(full_text_parts) or "(no answer)"
            assistant_payload = {
                "kind": "result",
                "model": model_used,
                "result": result_payload,
            }
            msg = DB.add_message(chat_id, "assistant", full_text, payload=assistant_payload)
            if notices:
                n = notices[-1]
                yield {"event": "notice", "data": json.dumps({
                    "kind": "model_fallback",
                    "from": n["from"],
                    "to": n["to"],
                    "reason": n["reason"],
                })}
            yield {"event": "done", "data": json.dumps({"message_id": msg["id"], "chat_id": chat_id})}
        except Exception as exc:
            log_event(LOGGERS["errors"], "query_error", request_id=request_id, error=str(exc))
            detail = str(exc)
            if "Binder Error" in detail or "TRY_CAST" in detail or "INVALID INPUT" in detail.upper():
                err_msg = "That query couldn't run against this dataset's column types — the date or numeric column may be stored as text. Try a non-time-grouped version of the question."
            elif "LLMUnavailable" in type(exc).__name__ or "RESOURCE_EXHAUSTED" in detail or "429" in detail:
                err_msg = "All language models are rate-limited right now. Wait a minute and retry."
            else:
                err_msg = "I couldn't answer that from the available data. (Internal error logged — check /opt/datachat/logs/errors.log)"
            DB.add_message(chat_id, "assistant", err_msg, payload={"kind": "error", "detail": detail})
            yield {"event": "error", "data": json.dumps({"message": err_msg, "detail": detail})}
            yield {"event": "done", "data": json.dumps({"chat_id": chat_id})}

    return EventSourceResponse(event_stream())
