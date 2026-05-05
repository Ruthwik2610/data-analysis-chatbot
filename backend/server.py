from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import logging
import math
import os
import re
import shutil
import socket
import sys
import time
import uuid
import zipfile
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
    prepare_pdf_source,
)
from src.logging_config import log_event, setup_loggers
from src.mcp_pool import extract_text_content, get_pool, parse_tool_result_to_dataframe
from src.model_router import LLMRouter, LLMUnavailable
from src.prompting import build_local_agent_system_prompt
from src.project_intelligence import (
    apply_instruction_rules,
    build_instruction_context,
    clarification_suggestions,
    default_source_instructions,
    detect_project_category,
    normalize_instructions,
)
from src.query_engine import (
    build_query_plan,
    build_total_plan,
    heuristic_intent,
    is_underspecified,
    quote_ident,
    underspecified_clarification,
    validate_readonly_sql,
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
PENDING: dict[str, dict[str, Any]] = {}  # upload_id -> { path, kind, file_name, created_at, ... }
PENDING_TTL_SECONDS = 1800
ARCHIVE_PDF_MAX_BYTES = int(float(os.getenv("ARCHIVE_PDF_MAX_MB", "0")) * 1024 * 1024)
DUCKDB_MEMORY_LIMIT = os.getenv("DUCKDB_MEMORY_LIMIT", "2GB")
DUCKDB_THREADS = max(1, int(os.getenv("DUCKDB_THREADS", "1")))


def _cleanup_pending(max_age_seconds: int = PENDING_TTL_SECONDS) -> None:
    cutoff = time.time() - max_age_seconds
    stale = [uid for uid, rec in list(PENDING.items()) if rec.get("created_at", 0) < cutoff]
    for uid in stale:
        rec = PENDING.pop(uid, {})
        path = rec.get("path")
        if not path:
            continue
        try:
            p = Path(path)
            if p.exists():
                p.unlink(missing_ok=True)
            if p.parent.exists() and not any(p.parent.iterdir()):
                p.parent.rmdir()
        except Exception:
            pass

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
ROUTER = LLMRouter(
    openrouter_api_key=CONFIG.openrouter_api_key,
    openrouter_provider_order=CONFIG.openrouter_provider_order,
    model=CONFIG.model,
    agent_model=CONFIG.agent_model,
    logger=LOGGERS["llm"],
    char_budget=CONFIG.prompt_char_budget,
)

MODEL_PRESETS = {
    "flash": {
        "model": os.getenv("MODEL_FLASH", "openrouter/deepseek/deepseek-v4-flash"),
        "agent_model": os.getenv("AGENT_MODEL_FLASH", os.getenv("MODEL_FLASH", "openrouter/deepseek/deepseek-v4-flash")),
        "provider_order": os.getenv("OPENROUTER_PROVIDER_ORDER_FLASH", CONFIG.openrouter_provider_order),
    },
    "pro": {
        "model": os.getenv("MODEL_PRO", CONFIG.model),
        "agent_model": os.getenv("AGENT_MODEL_PRO", CONFIG.agent_model),
        "provider_order": os.getenv("OPENROUTER_PROVIDER_ORDER_PRO", CONFIG.openrouter_provider_order),
    },
}
_ROUTER_CACHE: dict[str, LLMRouter] = {}


def _model_preset_for_mode(mode: str | None) -> dict[str, str]:
    normalized = (mode or "flash").strip().lower()
    return MODEL_PRESETS.get(normalized) or MODEL_PRESETS["flash"]


def _router_for_model_mode(mode: str | None) -> LLMRouter:
    preset = _model_preset_for_mode(mode)
    key = f"{preset['model']}::{preset['agent_model']}::{preset.get('provider_order', '')}"
    if key not in _ROUTER_CACHE:
        _ROUTER_CACHE[key] = LLMRouter(
            openrouter_api_key=CONFIG.openrouter_api_key,
            openrouter_provider_order=preset.get("provider_order", CONFIG.openrouter_provider_order),
            model=preset["model"],
            agent_model=preset["agent_model"],
            logger=LOGGERS["llm"],
            char_budget=CONFIG.prompt_char_budget,
        )
    return _ROUTER_CACHE[key]


PUBLIC_PATHS = {"/health"}


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-load saved MCP bridges (mcp.json) into the pool, then start the
    # background health-check loop. Both happen on the FastAPI event loop.
    pool = get_pool()
    try:
        await pool.auto_load(REPO_ROOT / "mcp_connectors.json")
        for state in pool.connectors.values():
            _persist_mcp_state(state, scope="global")
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
    if request.method == "OPTIONS" or not API_KEY or request.url.path in PUBLIC_PATHS:
        return await call_next(request)
    if request.headers.get("authorization") != f"Bearer {API_KEY}":
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
    return await call_next(request)


def _make_id(prefix: str = "src") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _safe_upload_filename(filename: str) -> str:
    name = Path(filename or "").name.strip()
    if not name:
        raise ValueError("Uploaded file name is empty")
    if name in {".", ".."}:
        raise ValueError("Uploaded file name is invalid")
    return name


def _workspace_table_name(source_id: str, display_name: str) -> str:
    stem = Path(display_name or "").stem
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", stem).strip("_").lower()
    if not slug:
        slug = re.sub(r"[^0-9a-zA-Z]+", "_", source_id).strip("_").lower() or "source"
    if not slug.startswith("src_"):
        slug = f"src_{slug}"
    return slug[:48]


def _column_type_family(col_type: Any) -> str:
    text = str(col_type or "").lower()
    if any(t in text for t in ("int", "double", "float", "decimal", "numeric", "real")):
        return "number"
    if any(t in text for t in ("date", "time")):
        return "time"
    return "text"


def _join_key_score(name: str) -> int:
    lowered = name.lower()
    score = 0
    if lowered == "id" or lowered.endswith("_id") or lowered.endswith("_key"):
        score += 4
    if any(term in lowered for term in ("customer", "cust", "user", "account", "order", "product", "prod", "sku")):
        score += 2
    return score


def _connect_duckdb(path: str = ":memory:", *, read_only: bool = False):
    import duckdb

    con = duckdb.connect(path, read_only=read_only)
    with contextlib.suppress(Exception):
        con.execute(f"SET threads={DUCKDB_THREADS}")
    with contextlib.suppress(Exception):
        con.execute(f"SET memory_limit='{DUCKDB_MEMORY_LIMIT}'")
    with contextlib.suppress(Exception):
        con.execute("SET preserve_insertion_order=false")
    return con


def _detect_join_candidates(source_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for i, left in enumerate(source_summaries):
        for right in source_summaries[i + 1:]:
            for lcol in left.get("columns", []):
                lname = lcol.get("name")
                if not lname:
                    continue
                lfamily = _column_type_family(lcol.get("type"))
                for rcol in right.get("columns", []):
                    rname = rcol.get("name")
                    if not rname:
                        continue
                    if lname != rname:
                        continue
                    if lfamily != _column_type_family(rcol.get("type")):
                        continue
                    score = _join_key_score(lname)
                    if score <= 0:
                        continue
                    candidates.append({
                        "left_source": left.get("id"),
                        "left_name": left.get("name"),
                        "left_table": left.get("table"),
                        "left_column": lname,
                        "right_source": right.get("id"),
                        "right_name": right.get("name"),
                        "right_table": right.get("table"),
                        "right_column": rname,
                        "confidence": min(0.95, 0.55 + score * 0.1),
                    })
    return sorted(candidates, key=lambda c: c["confidence"], reverse=True)


async def _assert_public_url(url: str) -> None:
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
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None)
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
    if DB.get_source_instructions(source_id) is None:
        DB.upsert_source_instructions(source_id, default_source_instructions(source.schema, source.display_name))
    DB.set_active_source(source_id)
    return _serialize_source(source_id, source, kind, active=True)


def _source_allowed_columns_from_row(row: dict[str, Any]) -> set[str]:
    try:
        schema = json.loads(row.get("schema_json") or "{}")
    except Exception:
        schema = {}
    return {str(c.get("name") or c.get("column")) for c in schema.get("columns", []) if c.get("name") or c.get("column")}


def _source_schema_from_row(row: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(row.get("schema_json") or "{}")
    except Exception:
        return {}


def _source_with_clarifications(result: dict[str, Any], source: DataSource) -> dict[str, Any]:
    suggestions = clarification_suggestions(source.schema, source.display_name)
    if suggestions:
        result = {**result, "clarifications": suggestions}
    return result


def _get_or_create_source_instructions(source_id: str) -> dict[str, Any]:
    existing = DB.get_source_instructions(source_id)
    if existing is not None:
        return existing
    row = DB.get_source(source_id)
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    instructions = default_source_instructions(_source_schema_from_row(row), row.get("name") or "")
    DB.upsert_source_instructions(source_id, instructions)
    return instructions


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
        if typ == "pdf":
            return await asyncio.to_thread(prepare_pdf_source, Path(origin["path"]), cache_logger)
        if typ == "api":
            await _assert_public_url(origin["url"])
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


def _metadata_description(name: str, tools: list[dict[str, Any]]) -> str:
    visible_tools = [t for t in tools if t.get("name")]
    if not visible_tools:
        return f"{name} is connected but has not exposed tools yet."
    names = ", ".join(str(t["name"]) for t in visible_tools[:8])
    if len(visible_tools) > 8:
        names += f", and {len(visible_tools) - 8} more"
    description_bits: list[str] = []
    for tool in visible_tools[:3]:
        desc = (tool.get("description") or "").strip().splitlines()[0]
        if desc:
            description_bits.append(f"{tool['name']}: {desc[:140]}")
    suffix = " " + " ".join(description_bits) if description_bits else ""
    return f"{name} exposes {len(visible_tools)} tool{'s' if len(visible_tools) != 1 else ''}: {names}.{suffix}"


def _state_transport(state: Any) -> str:
    return "stdio" if state.command else "http"


def _persist_mcp_state(state: Any, *, scope: str = "global", project_id: str | None = None) -> dict[str, Any]:
    normalized_scope = scope if scope in {"global", "project"} else "global"
    record = DB.upsert_mcp_connector(
        connector_id=state.id,
        name=state.name,
        scope=normalized_scope,
        transport=_state_transport(state),
        url=state.url,
        command=state.command,
        args=state.args,
        tools=state.tools if state.status == "connected" else [],
        status=state.status,
        last_error=state.last_error,
        description=_metadata_description(state.name, state.tools if state.status == "connected" else []),
        generated_description=None,
        description_status="metadata",
    )
    if project_id and normalized_scope == "project":
        DB.bind_mcp_to_project(project_id, state.id)
    return record


async def _refine_mcp_description_later(connector_id: str) -> None:
    if not ROUTER.available:
        return
    record = DB.get_mcp_connector(connector_id)
    if not record:
        return
    tool_lines = []
    for tool in record.get("tools", [])[:12]:
        desc = (tool.get("description") or "").strip().splitlines()[0]
        tool_lines.append(f"- {tool.get('name')}: {desc}" if desc else f"- {tool.get('name')}")
    prompt = (
        "Write one concise, factual sentence describing this data connector for a data-chat app. "
        "Do not mention MCP, tools, or implementation details.\n\n"
        f"Connector name: {record['name']}\n"
        f"Available operations:\n{chr(10).join(tool_lines)}"
    )
    try:
        text = await asyncio.to_thread(ROUTER._generate_text, prompt, uuid.uuid4().hex[:12])
        if text:
            DB.update_mcp_generated_description(connector_id, text[:600], "generated")
    except Exception:
        DB.update_mcp_generated_description(connector_id, None, "metadata")


def _serialize_mcp_connector(state: Any) -> dict[str, Any]:
    record = DB.get_mcp_connector(state.id)
    if record is None:
        record = _persist_mcp_state(state)
    tools = state.tools if state.status == "connected" else record.get("tools", [])
    return {
        "id": state.id,
        "name": state.name,
        "url": state.url,
        "status": state.status,
        "tools": tools,
        "last_error": state.last_error,
        "is_excel": hasattr(state, "_excel_connector"),
        "description": record.get("description"),
        "generated_description": record.get("generated_description"),
        "description_status": record.get("description_status", "metadata"),
        "scope": record.get("scope", "global"),
        "project_ids": DB.connector_project_ids(state.id),
    }


def _allowed_mcp_connector_ids_for_project(project_id: str | None) -> set[str]:
    return DB.allowed_mcp_connector_ids(project_id)


def _allowed_mcp_connector_ids_for_chat(chat_id: str | None) -> set[str]:
    if not chat_id:
        return _allowed_mcp_connector_ids_for_project(None)
    chat = DB.get_chat(chat_id)
    return _allowed_mcp_connector_ids_for_project(chat.get("project_id") if chat else None)


def _serialize_mcp_source(allowed_connector_ids: set[str] | None = None) -> dict[str, Any] | None:
    connected = [
        s for s in get_pool().connectors.values()
        if s.status == "connected" and (allowed_connector_ids is None or s.id in allowed_connector_ids)
    ]
    if not connected:
        return None
    tool_count = sum(len(s.tools) for s in connected)
    return {
        "id": "mcp",
        "name": ", ".join(s.name for s in connected),
        "kind": "mcp",
        "rows": tool_count,
        "columns": [],
        "active": False,
        "loaded": True,
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
    scope: str = "global"
    project_id: str | None = None


class MCPUpdate(BaseModel):
    name: str | None = None
    url: str | None = None


class AttachExcelMCP(BaseModel):
    path: str
    sheet: str | None = None


class ProjectCreate(BaseModel):
    title: str


class ProjectUpdate(BaseModel):
    title: str


class InstructionsUpdate(BaseModel):
    instructions: dict[str, Any]


class SourceClarificationUpdate(BaseModel):
    answers: dict[str, Any]


class ProjectAddFile(BaseModel):
    file_path: str | None = None
    source_id: str | None = None
    sheet: str | None = None


class ProjectNoteCreate(BaseModel):
    title: str | None = None
    content: str
    source_message_id: str | None = None


class ChatUpdateProject(BaseModel):
    project_id: str | None


class QueryRequest(BaseModel):
    chat_id: str | None = None
    question: str
    source_ids: list[str] | None = None
    project_id: str | None = None
    model_mode: str | None = None


# -- health ----------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# -- sources ---------------------------------------------------------------
@app.get("/sources")
def list_sources(project_id: str | None = None) -> list[dict[str, Any]]:
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
    mcp_source = _serialize_mcp_source(_allowed_mcp_connector_ids_for_project(project_id))
    if mcp_source:
        out.insert(0, mcp_source)
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
async def attach_api(body: AttachAPI) -> dict[str, Any]:
    await _assert_public_url(body.url)
    try:
        source = await asyncio.to_thread(prepare_api_source, body.url, LOGGERS["cache"], auth_header=body.auth)
        if body.ingest == "sql" and source.dataframe is not None:
            source = await asyncio.to_thread(dataframe_to_duckdb_source, source.dataframe, CONFIG.cache_dir, LOGGERS["cache"], body.url, "API SQL cache")
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

    con = _connect_duckdb(str(path), read_only=True)
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


def _extract_pdf_members_from_zip(zip_path: Path, destination_dir: Path) -> list[Path]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    pdf_paths: list[Path] = []
    used_names: set[str] = set()
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                member_name = Path(member.filename).name
                if not member_name or member_name.startswith("."):
                    continue
                if Path(member_name).suffix.lower() != ".pdf":
                    continue
                if ARCHIVE_PDF_MAX_BYTES > 0 and member.file_size > ARCHIVE_PDF_MAX_BYTES:
                    continue
                safe_name = _safe_upload_filename(member_name)
                stem = Path(safe_name).stem
                suffix = Path(safe_name).suffix
                candidate = safe_name
                counter = 2
                while candidate.lower() in used_names:
                    candidate = f"{stem}_{counter}{suffix}"
                    counter += 1
                used_names.add(candidate.lower())
                out_path = destination_dir / candidate
                with archive.open(member) as src, out_path.open("wb") as out:
                    shutil.copyfileobj(src, out)
                pdf_paths.append(out_path)
    except zipfile.BadZipFile as exc:
        raise ValueError("Uploaded ZIP file is not a valid archive.") from exc
    return pdf_paths


def _copy_archive_pdf_to_destination(source_path: Path, destination_dir: Path, original_name: str, used_names: set[str]) -> Path:
    safe_name = _safe_upload_filename(Path(original_name).name)
    stem = Path(safe_name).stem
    suffix = Path(safe_name).suffix
    candidate = safe_name
    counter = 2
    while candidate.lower() in used_names:
        candidate = f"{stem}_{counter}{suffix}"
        counter += 1
    used_names.add(candidate.lower())
    out_path = destination_dir / candidate
    shutil.copyfile(source_path, out_path)
    return out_path


def _extract_pdf_members_from_7z(archive_path: Path, destination_dir: Path) -> list[Path]:
    try:
        import py7zr
    except Exception as exc:  # pragma: no cover - dependency availability
        raise RuntimeError("7z extraction requires py7zr. Install requirements.txt first.") from exc

    destination_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = destination_dir / "_7z_staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()
    pdf_paths: list[Path] = []
    try:
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            targets = []
            for name in archive.getnames():
                path = Path(name)
                if path.is_absolute() or ".." in path.parts:
                    continue
                if path.name and not path.name.startswith(".") and path.suffix.lower() == ".pdf":
                    targets.append(name)
            if not targets:
                return []
            archive.extract(path=staging_dir, targets=targets)
        for name in targets:
            extracted = (staging_dir / name).resolve()
            if not str(extracted).startswith(str(staging_dir.resolve())) or not extracted.exists():
                continue
            pdf_paths.append(_copy_archive_pdf_to_destination(extracted, destination_dir, name, used_names))
    except py7zr.Bad7zFile as exc:
        raise ValueError("Uploaded 7z file is not a valid archive.") from exc
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
    return pdf_paths


def _extract_pdf_members_from_archive(archive_path: Path, destination_dir: Path) -> list[Path]:
    suffix = archive_path.suffix.lower()
    if suffix == ".zip":
        return _extract_pdf_members_from_zip(archive_path, destination_dir)
    if suffix == ".7z":
        return _extract_pdf_members_from_7z(archive_path, destination_dir)
    raise ValueError(f"Unsupported archive type: {suffix}")


def _archive_label(archive_path: Path) -> str:
    return "7z" if archive_path.suffix.lower() == ".7z" else "ZIP"


def _prepare_archive_pdf_sources(archive_path: Path, extraction_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    pdf_paths = _extract_pdf_members_from_archive(archive_path, extraction_dir)
    if not pdf_paths:
        raise ValueError(f"No PDF files found in this {_archive_label(archive_path)}.")

    attached: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for pdf_path in pdf_paths:
        try:
            if ARCHIVE_PDF_MAX_BYTES > 0 and pdf_path.stat().st_size > ARCHIVE_PDF_MAX_BYTES:
                max_mb = ARCHIVE_PDF_MAX_BYTES / (1024 * 1024)
                raise ValueError(
                    f"PDF is too large to auto-read from an archive (max {max_mb:.1f} MB). "
                    "Upload this PDF directly or export it to CSV/XLSX.",
                )
            source = prepare_pdf_source(pdf_path, LOGGERS["cache"])
            origin = {"type": "pdf", "path": str(pdf_path), "archive": str(archive_path)}
            attached.append(_persist_source(_make_id(), source, "pdf", origin))
        except Exception as exc:
            skipped.append({"file_name": pdf_path.name, "error": str(exc)})
    if not attached:
        details = "; ".join(f"{item['file_name']}: {item['error']}" for item in skipped[:5])
        raise ValueError(f"No readable PDF tables found in this {_archive_label(archive_path)}. {details}".strip())
    return attached, skipped


def _prepare_zip_pdf_sources(zip_path: Path, extraction_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    return _prepare_archive_pdf_sources(zip_path, extraction_dir)


@app.post("/sources/upload")
async def upload_source(file: UploadFile = File(...)) -> dict[str, Any]:
    _cleanup_pending()
    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")
    try:
        safe_name = _safe_upload_filename(file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    upload_id = uuid.uuid4().hex[:10]
    upload_dir = UPLOAD_DIR / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / safe_name
    # Stream the upload to disk on a worker thread so the event loop stays responsive.
    await asyncio.to_thread(_save_upload_sync, file.file, dest)

    suffix = dest.suffix.lower()
    file_name = safe_name
    size_mb = round(dest.stat().st_size / (1024 * 1024), 1)

    try:
        if suffix in {".xlsx", ".xls"}:
            sheets = await asyncio.to_thread(_list_excel_sheets, dest)
            if len(sheets) > 1:
                PENDING[upload_id] = {"path": str(dest), "file_name": file_name, "sheets": sheets, "kind": "xlsx", "created_at": time.time()}
                return {"pending": {
                    "kind": "sheet_pick",
                    "upload_id": upload_id,
                    "file_name": file_name,
                    "sheets": sheets,
                }}
            sheet = sheets[0] if sheets else None
            source = await asyncio.to_thread(prepare_excel_source, dest, sheet, LOGGERS["cache"])
            origin = {"type": "excel", "path": str(dest), "sheet": sheet, "ingest": "direct"}
            return _source_with_clarifications(_persist_source(_make_id(), source, "xlsx", origin), source)

        if suffix in {".duckdb", ".db"}:
            tables = await asyncio.to_thread(_list_duckdb_tables, dest)
            if len(tables) > 1:
                PENDING[upload_id] = {"path": str(dest), "file_name": file_name, "tables": tables, "kind": "duckdb", "created_at": time.time()}
                return {"pending": {
                    "kind": "table_pick",
                    "upload_id": upload_id,
                    "file_name": file_name,
                    "tables": tables,
                }}
            table = tables[0] if tables else "orders"
            source = await asyncio.to_thread(prepare_duckdb_source, dest, table, LOGGERS["cache"])
            origin = {"type": "duckdb", "path": str(dest), "table": table}
            return _source_with_clarifications(_persist_source(_make_id(), source, "duckdb", origin), source)

        if suffix == ".csv":
            if size_mb > 100:
                PENDING[upload_id] = {"path": str(dest), "file_name": file_name, "size_mb": size_mb, "kind": "csv", "created_at": time.time()}
                return {"pending": {
                    "kind": "ingest_pick",
                    "upload_id": upload_id,
                    "file_name": file_name,
                    "size_mb": size_mb,
                }}
            source = await asyncio.to_thread(prepare_csv_memory_source, dest, LOGGERS["cache"])
            origin = {"type": "csv_memory", "path": str(dest)}
            return _source_with_clarifications(_persist_source(_make_id(), source, "csv", origin), source)

        if suffix == ".json":
            from src.data_sources import prepare_local_file_source

            source = await asyncio.to_thread(
                prepare_local_file_source,
                dest, CONFIG.cache_dir, LOGGERS["cache"], "orders", None, False, "direct",
            )
            origin = {"type": "json", "path": str(dest)}
            return _source_with_clarifications(_persist_source(_make_id(), source, "json", origin), source)

        if suffix == ".pdf":
            source = await asyncio.to_thread(prepare_pdf_source, dest, LOGGERS["cache"])
            origin = {"type": "pdf", "path": str(dest)}
            return _source_with_clarifications(_persist_source(_make_id(), source, "pdf", origin), source)

        if suffix in {".zip", ".7z"}:
            sources, skipped = await asyncio.to_thread(_prepare_archive_pdf_sources, dest, upload_dir / "unpacked")
            return {"sources": sources, "skipped": skipped}

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
            result = _source_with_clarifications(_persist_source(_make_id(), source, "xlsx", origin), source)
        elif record["kind"] == "duckdb":
            source = prepare_duckdb_source(path, body.value, logger=LOGGERS["cache"])
            origin = {"type": "duckdb", "path": str(path), "table": body.value}
            result = _source_with_clarifications(_persist_source(_make_id(), source, "duckdb", origin), source)
        elif record["kind"] == "csv":
            ingest = body.value if body.value in ("direct", "sql") else "direct"
            if ingest == "sql":
                source = prepare_csv_source(path, CONFIG.cache_dir, logger=LOGGERS["cache"], force=False)
            else:
                source = prepare_csv_memory_source(path, logger=LOGGERS["cache"])
            origin = {"type": f"csv_{ingest}", "path": str(path)}
            result = _source_with_clarifications(_persist_source(_make_id(), source, "csv", origin), source)
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


@app.get("/sources/{source_id}/instructions")
def get_source_instructions(source_id: str) -> dict[str, Any]:
    row = DB.get_source(source_id)
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    instructions = _get_or_create_source_instructions(source_id)
    return {"source_id": source_id, "instructions": instructions}


@app.patch("/sources/{source_id}/instructions")
def update_source_instructions(source_id: str, body: InstructionsUpdate) -> dict[str, Any]:
    row = DB.get_source(source_id)
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    normalized = normalize_instructions(body.instructions, _source_allowed_columns_from_row(row))
    return DB.upsert_source_instructions(source_id, normalized)


@app.post("/sources/{source_id}/clarifications")
def apply_source_clarifications(source_id: str, body: SourceClarificationUpdate) -> dict[str, Any]:
    row = DB.get_source(source_id)
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    allowed = _source_allowed_columns_from_row(row)
    instructions = _get_or_create_source_instructions(source_id)
    answers = body.answers or {}
    if answers.get("row_grain"):
        instructions["row_grain"] = str(answers["row_grain"])
    normalized = normalize_instructions(instructions, allowed)
    return DB.upsert_source_instructions(source_id, normalized)


# -- chats -----------------------------------------------------------------
@app.get("/chats")
def list_chats() -> list[dict[str, Any]]:
    return DB.list_chats()


async def ensure_project_context(project_id: str):
    project = DB.get_project(project_id)
    if not project:
        return
    
    pool = get_pool()
    for file_rec in project["files"]:
        path = None
        if file_rec.get("source_id"):
            path = UPLOAD_DIR / file_rec["source_id"]
        elif file_rec.get("file_path"):
            path = Path(file_rec["file_path"]).expanduser()
        
        if not path or not path.exists():
            logging.warning(f"Project file not found: {path}")
            continue
        
        # dedup_key matches the logic in attach_excel_mcp
        dedup_key = f"excel-mcp::{path.resolve()}::{path.stat().st_mtime_ns}::{file_rec['sheet_name'] or 0}"
        
        # Check if already in pool
        exists = False
        for cid, s in pool.connectors.items():
            if getattr(s, "_dedup_key", None) == dedup_key:
                exists = True
                break
        
        if not exists:
            try:
                source = await asyncio.to_thread(prepare_excel_source, path, file_rec['sheet_name'], LOGGERS["cache"])
                if source.dataframe is not None and not source.dataframe.empty:
                    await pool.connect_excel(df=source.dataframe, display_name=path.name, dedup_key=dedup_key)
            except Exception as exc:
                logging.error(f"Failed to auto-load project file {path}: {exc}")


@app.get("/chats/{chat_id}")
async def get_chat(chat_id: str) -> dict[str, Any]:
    chat = DB.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    if chat.get("project_id"):
        await ensure_project_context(chat["project_id"])
        
    return chat


@app.post("/chats")
def create_chat() -> dict[str, Any]:
    return DB.create_chat()


@app.delete("/chats/{chat_id}")
def delete_chat(chat_id: str) -> dict[str, Any]:
    DB.delete_chat(chat_id)
    return {"ok": True}


@app.patch("/chats/{chat_id}/project")
def update_chat_project(chat_id: str, body: ChatUpdateProject) -> dict[str, Any]:
    DB.update_chat_project(chat_id, body.project_id)
    return {"ok": True}


# -- projects --------------------------------------------------------------
@app.get("/projects")
def list_projects() -> list[dict[str, Any]]:
    return DB.list_projects()


@app.post("/projects")
def create_project(body: ProjectCreate) -> dict[str, Any]:
    return DB.create_project(body.title)


@app.get("/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    p = DB.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@app.patch("/projects/{project_id}")
def update_project(project_id: str, body: ProjectUpdate) -> dict[str, Any]:
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Project title is required")
    p = DB.update_project(project_id, title)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@app.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, Any]:
    DB.delete_project(project_id)
    return {"ok": True}


@app.get("/projects/{project_id}/instructions")
def get_project_instructions(project_id: str) -> dict[str, Any]:
    project = DB.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    instructions = DB.get_project_instructions(project_id)
    if instructions is None:
        source_rows = [DB.get_source(f.get("source_id")) for f in project.get("files", []) if f.get("source_id")]
        instructions = {"category": detect_project_category(project, [r for r in source_rows if r]), "notes": "", "metrics": {}, "entities": {}}
        DB.upsert_project_instructions(project_id, instructions)
    return {"project_id": project_id, "instructions": instructions}


@app.patch("/projects/{project_id}/instructions")
def update_project_instructions(project_id: str, body: InstructionsUpdate) -> dict[str, Any]:
    if not DB.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    instructions = dict(body.instructions or {})
    category = str(instructions.get("category") or "").strip().lower()
    if category and category not in {"general", "sales", "finance", "inventory", "operations", "customer_support"}:
        instructions["category"] = "general"
    return DB.upsert_project_instructions(project_id, instructions)


@app.post("/projects/{project_id}/profile/rebuild")
def rebuild_project_profile(project_id: str) -> dict[str, Any]:
    project = DB.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    existing = DB.get_project_instructions(project_id) or {}
    if not existing.get("category"):
        source_rows = [DB.get_source(f.get("source_id")) for f in project.get("files", []) if f.get("source_id")]
        existing["category"] = detect_project_category(project, [r for r in source_rows if r])
    saved = DB.upsert_project_instructions(project_id, existing)
    DB.rebuild_project_memory(project_id)
    return saved


@app.post("/projects/{project_id}/files")
def add_project_file(project_id: str, body: ProjectAddFile) -> dict[str, Any]:
    if body.source_id:
        # Check if source exists
        s = DB.get_source(body.source_id)
        if not s:
            raise HTTPException(status_code=404, detail="Source not found")
        return DB.add_file_to_project(project_id, None, source_id=body.source_id, sheet_name=body.sheet)
    
    if not body.file_path:
        raise HTTPException(status_code=400, detail="file_path or source_id required")
        
    path = Path(body.file_path).expanduser()
    if not path.exists():
        raise HTTPException(status_code=400, detail="File not found")
    return DB.add_file_to_project(project_id, str(path), sheet_name=body.sheet)


@app.delete("/projects/{project_id}/files/{file_id}")
def delete_project_file(project_id: str, file_id: str) -> dict[str, Any]:
    DB.remove_file_from_project(project_id, file_id)
    return {"ok": True}


@app.get("/projects/{project_id}/notes")
def list_project_notes(project_id: str) -> list[dict[str, Any]]:
    if not DB.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return DB.list_project_notes(project_id)


@app.post("/projects/{project_id}/notes")
def create_project_note(project_id: str, body: ProjectNoteCreate) -> dict[str, Any]:
    if not DB.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Note content is required")
    return DB.add_project_note(
        project_id,
        body.title or "Saved analysis",
        content,
        source_message_id=body.source_message_id,
    )


@app.delete("/projects/{project_id}/notes/{note_id}")
def delete_project_note(project_id: str, note_id: str) -> dict[str, Any]:
    if not DB.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    DB.delete_project_note(project_id, note_id)
    return {"ok": True}


@app.get("/projects/{project_id}/mcp")
def list_project_mcp(project_id: str) -> list[dict[str, Any]]:
    if not DB.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return DB.list_project_mcp_connectors(project_id)


@app.post("/projects/{project_id}/mcp/{connector_id}")
def bind_project_mcp(project_id: str, connector_id: str) -> dict[str, Any]:
    if not DB.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    if not DB.get_mcp_connector(connector_id):
        raise HTTPException(status_code=404, detail="MCP connector not found")
    DB.bind_mcp_to_project(project_id, connector_id)
    return {"ok": True}


@app.delete("/projects/{project_id}/mcp/{connector_id}")
def unbind_project_mcp(project_id: str, connector_id: str) -> dict[str, Any]:
    if not DB.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    DB.unbind_mcp_from_project(project_id, connector_id)
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
    return [_serialize_mcp_connector(s) for s in get_pool().connectors.values()]


@app.post("/mcp/connectors")
async def add_mcp_connector(body: MCPConnect) -> dict[str, Any]:
    if not body.url.strip():
        raise HTTPException(status_code=400, detail="url is required")
    await _assert_public_url(body.url.strip())
    cid = await get_pool().connect(url=body.url.strip(), name=body.name or body.url.strip())
    state = get_pool().connectors.get(cid)
    if state and state.status == "error":
        _persist_mcp_state(state, scope=body.scope, project_id=body.project_id)
        raise HTTPException(status_code=400, detail=state.last_error or "Failed to connect to MCP bridge")
    if not state:
        raise HTTPException(status_code=400, detail="Connector state was not created")
    _persist_mcp_state(state, scope=body.scope, project_id=body.project_id)
    asyncio.create_task(_refine_mcp_description_later(cid))
    return _serialize_mcp_connector(state)


@app.put("/mcp/connectors/{connector_id}")
async def update_mcp_connector(connector_id: str, body: MCPUpdate) -> dict[str, Any]:
    pool = get_pool()
    state = pool.connectors.get(connector_id)
    if not state:
        raise HTTPException(status_code=404, detail="Connector not found")
    requested_url = body.url.strip() if body.url and body.url.strip() else state.url
    requested_name = body.name or state.name
    if body.url is not None:
        await _assert_public_url(requested_url)
        await pool.connect(url=requested_url, name=requested_name, connector_id=connector_id)
        state = pool.connectors[connector_id]
        if state.status == "error":
            raise HTTPException(status_code=400, detail=state.last_error or "Reconnect failed")
    elif body.name:
        await pool.rename(connector_id, body.name)
    state = pool.connectors[connector_id]
    record = DB.get_mcp_connector(connector_id)
    _persist_mcp_state(state, scope=record.get("scope", "global") if record else "global")
    return _serialize_mcp_connector(state)


@app.delete("/mcp/connectors/{connector_id}")
async def remove_mcp_connector(connector_id: str) -> dict[str, Any]:
    ok = await get_pool().disconnect(connector_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Connector not found")
    return {"ok": True}


EXCEL_MCP_MAX_BYTES = 50 * 1024 * 1024  # 50MB


@app.post("/mcp/excel")
async def attach_excel_mcp(body: AttachExcelMCP) -> dict[str, Any]:
    path = Path(body.path).expanduser()
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {body.path}")
    if path.suffix.lower() not in {".xlsx", ".xls"}:
        raise HTTPException(status_code=400, detail="Only .xlsx and .xls files are supported for Excel MCP")
    if path.stat().st_size > EXCEL_MCP_MAX_BYTES:
        raise HTTPException(status_code=400, detail="File too large for in-process MCP (max 50MB)")

    # dedup_key includes path, mtime, and sheet
    dedup_key = f"excel-mcp::{path.resolve()}::{path.stat().st_mtime_ns}::{body.sheet or 0}"
    pool = get_pool()
    for cid, s in pool.connectors.items():
        if getattr(s, "_dedup_key", None) == dedup_key:
            return _serialize_mcp_connector(s)

    try:
        source = await asyncio.to_thread(prepare_excel_source, path, body.sheet, LOGGERS["cache"])
        df = source.dataframe
        if df is None or df.empty:
            raise ValueError("Sheet has no data")
        
        cid = await pool.connect_excel(df=df, display_name=path.name, dedup_key=dedup_key)
        state = pool.connectors[cid]
        _persist_mcp_state(state, scope="global")
        asyncio.create_task(_refine_mcp_description_later(cid))
        return _serialize_mcp_connector(state)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to load Excel: {exc}")


@app.post("/connectors/{connector_id}/use")
async def use_connector(connector_id: str) -> dict[str, Any]:
    record = DB.get_connector(connector_id)
    if not record:
        raise HTTPException(status_code=404, detail="Connector not found")
    cfg = record["config"]
    try:
        if record["kind"] == "api":
            await _assert_public_url(cfg["url"])
            source = await asyncio.to_thread(prepare_api_source, cfg["url"], LOGGERS["cache"], auth_header=cfg.get("auth"))
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
    for row in head.itertuples(index=False, name=None):
        cleaned: list[Any] = []
        for v in row:
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                cleaned.append(None)
            elif pd.isna(v):
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


def _sanitize_assistant_text(text: str) -> str:
    # 1. Remove DSML tool call markup
    text = re.sub(r"<｜｜DSML｜｜tool_calls>.*?</｜｜DSML｜｜tool_calls>", "", text, flags=re.DOTALL)
    text = text.strip()

    # 2. Cap long bulleted lists to 5 items
    lines = text.splitlines()
    bullet_indices = [i for i, line in enumerate(lines) if line.strip().startswith("- ")]
    if len(bullet_indices) > 5:
        # Keep text before the first bullet
        first_bullet_idx = bullet_indices[0]
        # Keep first 5 bullets
        last_allowed_bullet_idx = bullet_indices[4]
        
        new_lines = lines[:last_allowed_bullet_idx + 1]
        new_lines.append(f" (showing first 5 items out of {len(bullet_indices)})")
        
        # Keep text after the last bullet
        last_bullet_idx = bullet_indices[-1]
        new_lines.extend(lines[last_bullet_idx + 1:])
        text = "\n".join(new_lines)
    
    return text.strip()


def _result_grounded_answer(question: str, payload: dict[str, Any]) -> str:
    row_count = payload.get("row_count", 0)
    columns = payload.get("columns", [])
    rows = payload.get("rows", [])
    truncated = payload.get("truncated", False)

    # Month-wise orders summary
    if "month wise orders" in question.lower() and "vno" in columns and "period" in columns:
        parts = []
        p_idx = columns.index("period")
        v_idx = columns.index("vno")
        for r in rows:
            period = r[p_idx]
            count = r[v_idx]
            formatted = _format_period_for_llm(period)
            parts.append(f"{formatted}: **{count:,} distinct orders**")
        return "; ".join(parts) + "."

    # Product count summary
    if "product" in question.lower() and "product_count" in columns:
        count = rows[0][columns.index("product_count")]
        return f"I found **{count:,} matching products**. The verified count is shown below."

    # General list summary
    if row_count > 0:
        count_str = f"{row_count:,}"
        if truncated:
            return f"I found **{count_str} matching products**. The result card below includes a table preview and CSV download with the first {len(rows)} rows."
        return f"I found **{count_str} matching products**. The result card below includes a verified table preview and CSV download."

    return ""


def _run_query(plan, source: DataSource) -> tuple[pd.DataFrame, int]:
    import duckdb

    start = time.perf_counter()
    p_key = params_key(plan.params)
    if source.db_path:
        params = json.loads(p_key)
        con = _connect_duckdb(source.db_path, read_only=True)
        try:
            if source.table_name != "orders":
                safe_table = '"' + source.table_name.replace('"', '""') + '"'
                con.execute(f"CREATE TEMP VIEW orders AS SELECT * FROM {safe_table}")
            df = con.execute(plan.sql, params).fetchdf()
        finally:
            con.close()
    elif source.dataframe is not None:
        params = json.loads(p_key)
        con = _connect_duckdb(":memory:")
        try:
            con.register("orders", source.dataframe)
            df = con.execute(plan.sql, params).fetchdf()
        finally:
            con.close()
    else:
        raise RuntimeError("No executable source")
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return df, elapsed_ms


def _table_schema_from_duckdb(con: Any, table_name: str) -> list[dict[str, str]]:
    rows = con.execute(f"PRAGMA table_info({quote_ident(table_name)})").fetchall()
    return [{"name": str(r[1]), "type": str(r[2])} for r in rows]


def _prepare_workspace_sync(chat_id: str, selected: list[tuple[dict[str, Any], DataSource]]) -> list[dict[str, Any]]:
    import duckdb

    work_dir = CONFIG.cache_dir / "workspaces"
    work_dir.mkdir(parents=True, exist_ok=True)
    work_path = work_dir / f"{chat_id}.duckdb"
    con = _connect_duckdb(str(work_path))
    summaries: list[dict[str, Any]] = []
    used_tables: set[str] = set()
    try:
        for idx, (row, source) in enumerate(selected):
            base_table = _workspace_table_name(row["id"], row["name"])
            table = base_table
            suffix = 2
            while table in used_tables:
                table = f"{base_table[:42]}_{suffix}"
                suffix += 1
            used_tables.add(table)

            if source.db_path:
                alias = f"db_{idx}"
                db_path = str(source.db_path).replace("'", "''")
                with contextlib.suppress(Exception):
                    con.execute(f"DETACH {quote_ident(alias)}")
                con.execute(f"ATTACH '{db_path}' AS {quote_ident(alias)} (READ_ONLY)")
                con.execute(
                    f"CREATE OR REPLACE TABLE {quote_ident(table)} AS "
                    f"SELECT * FROM {quote_ident(alias)}.{quote_ident(source.table_name)}"
                )
            elif source.dataframe is not None:
                temp_name = f"df_{idx}"
                con.register(temp_name, source.dataframe)
                con.execute(f"CREATE OR REPLACE TABLE {quote_ident(table)} AS SELECT * FROM {quote_ident(temp_name)}")
                con.unregister(temp_name)
            else:
                continue

            columns = _table_schema_from_duckdb(con, table)
            summaries.append({
                "id": row["id"],
                "name": row["name"],
                "kind": row["kind"],
                "table": table,
                "rows": source.row_count,
                "columns": columns,
            })
    finally:
        con.close()
    return summaries


def _run_workspace_sql_sync(chat_id: str, sql: str) -> tuple[pd.DataFrame, int]:
    import duckdb

    chat_id = Path(chat_id).name
    work_path = CONFIG.cache_dir / "workspaces" / f"{chat_id}.duckdb"
    start = time.perf_counter()
    con = _connect_duckdb(str(work_path), read_only=True)
    try:
        df = con.execute(sql).fetchdf()
    finally:
        con.close()
    return df, int((time.perf_counter() - start) * 1000)


def _materialize_workspace_df_sync(chat_id: str, table_name: str, df: pd.DataFrame) -> dict[str, Any]:
    import duckdb

    chat_id = Path(chat_id).name
    work_path = CONFIG.cache_dir / "workspaces" / f"{chat_id}.duckdb"
    con = _connect_duckdb(str(work_path))
    try:
        con.register("mcp_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {quote_ident(table_name)} AS SELECT * FROM mcp_df")
        con.unregister("mcp_df")
        columns = _table_schema_from_duckdb(con, table_name)
    finally:
        con.close()
    return {"table": table_name, "rows": int(len(df)), "columns": columns}


def _workspace_prompt(source_summaries: list[dict[str, Any]], connector_summary: str, join_candidates: list[dict[str, Any]]) -> str:
    source_lines: list[str] = []
    for src in source_summaries:
        cols = ", ".join(f"{c['name']}:{c['type']}" for c in src.get("columns", [])[:40])
        source_lines.append(f"- {src['name']} as table {src['table']} ({src['rows']} rows): {cols}")
    join_lines = [
        f"- {c['left_table']}.{c['left_column']} = {c['right_table']}.{c['right_column']} (confidence {c['confidence']:.2f})"
        for c in join_candidates[:10]
    ]
    return f"""You are a multi-source data analyst. Use tools to retrieve data and run DuckDB SQL.

## Local workspace tables
{chr(10).join(source_lines) if source_lines else "- No local tables loaded yet. Use connected tools to fetch data first."}

## Suggested join keys
{chr(10).join(join_lines) if join_lines else "- No confident join keys detected. If a join is needed, ask the user which columns relate before guessing."}

## Connected live sources
{connector_summary or "(no MCP bridges connected)"}

## Rules
- For local workspace data, call run_sql with SELECT statements against the table names above.
- For live MCP/API-style data, call the relevant tool first. Tabular tool results are cached into workspace tables and the tool response will name the new table.
- When a question needs a join and the relationship is unclear, ask one short clarification question instead of guessing.
- Never mention MCP, tool internals, or function calls in the final answer unless the user asks.
- Keep final answers to one short sentence. The result table/chart appears below your answer.
"""


def _build_mcp_summary(pool, allowed_connector_ids: set[str] | None = None) -> str:
    """Compact text describing connected MCP bridges and their tools, for the
    intent classifier to decide whether to route a question to MCP."""
    lines: list[str] = []
    for s in pool.connectors.values():
        if allowed_connector_ids is not None and s.id not in allowed_connector_ids:
            continue
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
    allowed_connector_ids: set[str] | None = None,
    llm_router: LLMRouter | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Drive the function-calling agent loop, stream SSE events, and persist the
    final assistant message. Picks the LAST tabular tool result (>=2 rows,
    >=2 cols) and emits it as a `result` event so ResultBlock renders a chart.
    The agent's natural sequence is explore (describe/list) → fetch (query/get) →
    answer; the data the user actually asked for is always the last fetch."""
    router = llm_router or ROUTER
    pool = get_pool()
    specs, routing = pool.aggregate_tools(allowed_connector_ids=allowed_connector_ids)
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
        if allowed_connector_ids is not None and s.id not in allowed_connector_ids:
            continue
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
            df = await asyncio.to_thread(parse_tool_result_to_dataframe, text)
            if df is not None:
                collected_dfs.append((tool_name, df))
            # Truncate text fed back to LLM to keep context lean.
            if len(text) > 6000:
                text = text[:6000] + f"\n\n[truncated at 6000 of {len(text)} chars]"
            return text, None, connector_id
        except Exception as exc:
            return "", str(exc), connector_id

    full_text_parts: list[str] = []
    last_tool_call: dict[str, Any] | None = None

    try:
        async for ev in router.agent_loop_stream(
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

    # Pick the LAST tabular tool result for charting (see docstring for rationale).
    result_payload: dict[str, Any] | None = None
    if collected_dfs:
        tool_name, df = collected_dfs[-1]
        viz = choose_visualization(question, {}, df)
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


async def _run_local_agent(
    chat_id: str,
    question: str,
    source: DataSource,
    history: list[dict[str, Any]],
    request_id: str,
    model_used: str,
    llm_router: LLMRouter | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Drive a function-calling loop against the local DuckDB source.

    Used when the intent classifier picks intent_type="multi_step" — the question
    chains two queries where the second depends on the first's result. The LLM
    calls run_sql once to find the anchor (e.g. peak month), reads the result,
    then calls run_sql again parameterized by that anchor."""
    router = llm_router or ROUTER
    system_prompt = build_local_agent_system_prompt(source.display_name, source.schema)

    tool_specs = [{
        "name": "run_sql",
        "description": "Execute a read-only DuckDB SELECT against the local dataset (table name 'orders'). Returns matching rows as JSON records.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "DuckDB SELECT query."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    }]

    collected: list[tuple[str, pd.DataFrame]] = []
    loop = asyncio.get_event_loop()

    def _run_sql_blocking(sql: str) -> pd.DataFrame:
        import duckdb
        if source.db_path:
            con = _connect_duckdb(source.db_path, read_only=True)
            try:
                if source.table_name != "orders":
                    safe = '"' + source.table_name.replace('"', '""') + '"'
                    con.execute(f"CREATE TEMP VIEW orders AS SELECT * FROM {safe}")
                return con.execute(sql).fetchdf()
            finally:
                con.close()
        if source.dataframe is not None:
            con = _connect_duckdb(":memory:")
            try:
                con.register("orders", source.dataframe)
                return con.execute(sql).fetchdf()
            finally:
                con.close()
        raise RuntimeError("No executable source")

    async def on_tool_call(tool_name: str, args: dict[str, Any]):
        if tool_name != "run_sql":
            return "", f"Unknown tool: {tool_name}", None
        sql = (args.get("query") or "").strip()
        try:
            validate_readonly_sql(sql)
        except Exception as exc:
            return "", f"SQL rejected: {exc}", None
        try:
            df = await loop.run_in_executor(None, _run_sql_blocking, sql)
        except Exception as exc:
            return "", str(exc), None
        if not df.empty:
            collected.append((sql, df))
        records = df.head(50).to_dict(orient="records")
        text = json.dumps(records, default=str)
        if len(text) > 6000:
            text = text[:6000] + f"\n[truncated, total rows: {len(df)}]"
        return text, None, "local"

    full_text_parts: list[str] = []

    try:
        async for ev in router.agent_loop_stream(
            request_id=request_id,
            user_question=question,
            conversation_summary=conversation_summary(history),
            tool_specs=tool_specs,
            connector_summary="",
            on_tool_call=on_tool_call,
            system_prompt=system_prompt,
        ):
            kind = ev["kind"]
            if kind == "tool_call":
                sql_arg = (ev.get("args") or {}).get("query", "")
                preview = sql_arg.replace("\n", " ").strip()[:120]
                step = f"Querying: {preview}{'…' if len(sql_arg) > 120 else ''}"
                yield {"event": "thinking", "data": json.dumps({"step": step})}
            elif kind == "tool_result":
                if ev.get("error"):
                    yield {"event": "thinking", "data": json.dumps({"step": "Query returned an error — adjusting"})}
                else:
                    yield {"event": "thinking", "data": json.dumps({"step": "Got data"})}
            elif kind == "text":
                full_text_parts.append(ev["delta"])
                yield {"event": "text", "data": json.dumps({"delta": ev["delta"]})}
    except LLMUnavailable as exc:
        err_msg = "All language models are rate-limited right now. Wait a minute and retry."
        DB.add_message(chat_id, "assistant", err_msg, payload={"kind": "error", "detail": str(exc)})
        yield {"event": "error", "data": json.dumps({"message": err_msg, "detail": str(exc)})}
        yield {"event": "done", "data": json.dumps({"chat_id": chat_id})}
        return

    full_text = "".join(full_text_parts).strip() or "(no answer)"

    # The last successful query's result is the chart card.
    result_payload: dict[str, Any] | None = None
    if collected:
        sql, df = collected[-1]
        viz = choose_visualization(question, {}, df)
        result_payload = {
            "title": "Multi-step Result",
            "viz": viz,
            "elapsed_ms": 0,
            "sql": sql,
            "how": f"Source: {source.source_kind}. Model: {model_used}. Multi-step query (final). Display: {viz}.",
            **_df_to_payload(df),
        }
        yield {"event": "result", "data": json.dumps(result_payload, default=str)}

    payload: dict[str, Any] = {"kind": "result" if result_payload else "text", "model": model_used}
    if result_payload:
        payload["result"] = result_payload
    msg = DB.add_message(chat_id, "assistant", full_text, payload=payload)
    yield {"event": "done", "data": json.dumps({"message_id": msg["id"], "chat_id": chat_id})}


async def _run_multi_source_agent(
    chat_id: str,
    question: str,
    selected: list[tuple[dict[str, Any], DataSource]],
    history: list[dict[str, Any]],
    request_id: str,
    allowed_connector_ids: set[str] | None = None,
    llm_router: LLMRouter | None = None,
) -> AsyncIterator[dict[str, Any]]:
    router = llm_router or ROUTER
    pool = get_pool()
    specs, routing = pool.aggregate_tools(allowed_connector_ids=allowed_connector_ids)
    loop = asyncio.get_running_loop()
    source_summaries = await loop.run_in_executor(None, lambda: _prepare_workspace_sync(chat_id, selected))
    join_candidates = _detect_join_candidates(source_summaries)

    connector_summary_lines: list[str] = []
    name_lookup: dict[str, str] = {}
    by_connector: dict[str, list[str]] = {}
    for s in pool.connectors.values():
        if allowed_connector_ids is not None and s.id not in allowed_connector_ids:
            continue
        if s.status == "connected":
            name_lookup[s.id] = s.name
            by_connector.setdefault(s.id, []).extend(t["name"] for t in s.tools)
    for cid, tnames in by_connector.items():
        connector_summary_lines.append(f"### {name_lookup[cid]} · {len(tnames)} tools\n  - " + "\n  - ".join(tnames))
    connector_summary = "\n\n".join(connector_summary_lines)

    tool_specs = [{
        "name": "run_sql",
        "description": "Execute a read-only DuckDB SELECT against the per-chat workspace tables. Use this for joins, aggregation, filtering, and final result shaping.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "DuckDB SELECT query against workspace tables."}},
            "required": ["query"],
            "additionalProperties": False,
        },
    }] + specs

    if len(tool_specs) == 1 and not source_summaries:
        msg_text = "I don't have any usable sources yet. Attach a file, connect an API, or add an MCP bridge first."
        msg = DB.add_message(chat_id, "assistant", msg_text, payload={"kind": "error"})
        yield {"event": "text", "data": json.dumps({"delta": msg_text})}
        yield {"event": "done", "data": json.dumps({"message_id": msg["id"], "chat_id": chat_id})}
        return

    collected: list[tuple[str, pd.DataFrame, int]] = []
    materialized_count = 0

    async def on_tool_call(tool_name: str, args: dict[str, Any]):
        nonlocal materialized_count
        if tool_name == "run_sql":
            sql = (args.get("query") or "").strip()
            try:
                validate_readonly_sql(sql)
            except Exception as exc:
                return "", f"SQL rejected: {exc}", None
            try:
                df, elapsed_ms = await loop.run_in_executor(None, lambda: _run_workspace_sql_sync(chat_id, sql))
            except Exception as exc:
                return "", str(exc), None
            collected.append((sql, df, elapsed_ms))
            text = json.dumps(df.head(50).to_dict(orient="records"), default=str)
            if len(text) > 6000:
                text = text[:6000] + f"\n[truncated, total rows: {len(df)}]"
            return text, None, "workspace"

        connector_id = routing.get(tool_name)
        if not connector_id:
            return "", f"Tool '{tool_name}' is not available.", None
        try:
            result = await pool.call_tool(connector_id, tool_name, args)
            text = extract_text_content(result)
            df = await asyncio.to_thread(parse_tool_result_to_dataframe, text)
            if df is not None:
                materialized_count += 1
                table = f"mcp_{re.sub(r'[^0-9a-zA-Z]+', '_', tool_name).strip('_').lower()[:28]}_{materialized_count}"
                info = await loop.run_in_executor(None, lambda: _materialize_workspace_df_sync(chat_id, table, df))
                source_summaries.append({
                    "id": f"mcp:{tool_name}:{materialized_count}",
                    "name": f"{tool_name} result",
                    "kind": "mcp",
                    **info,
                })
                cols = ", ".join(f"{c['name']}:{c['type']}" for c in info["columns"][:30])
                text += f"\n\n[Cached this tabular result as workspace table {table} with {info['rows']} rows. Columns: {cols}]"
            if len(text) > 6000:
                text = text[:6000] + f"\n\n[truncated at 6000 of {len(text)} chars]"
            return text, None, connector_id
        except Exception as exc:
            return "", str(exc), connector_id

    full_text_parts: list[str] = []
    try:
        async for ev in router.agent_loop_stream(
            request_id=request_id,
            user_question=question,
            conversation_summary=conversation_summary(history),
            tool_specs=tool_specs,
            connector_summary=connector_summary,
            on_tool_call=on_tool_call,
            system_prompt=_workspace_prompt(source_summaries, connector_summary, join_candidates),
        ):
            kind = ev["kind"]
            if kind == "tool_call":
                if ev["name"] == "run_sql":
                    sql_arg = (ev.get("args") or {}).get("query", "")
                    preview = sql_arg.replace("\n", " ").strip()[:120]
                    yield {"event": "thinking", "data": json.dumps({"step": f"Querying workspace: {preview}{'…' if len(sql_arg) > 120 else ''}"})}
                else:
                    connector_id = routing.get(ev["name"])
                    cname = name_lookup.get(connector_id, "connected source")
                    yield {"event": "thinking", "data": json.dumps({"step": f"Fetching data from {cname}"})}
            elif kind == "tool_result":
                if ev.get("error"):
                    yield {"event": "thinking", "data": json.dumps({"step": f"{ev['name']} returned an error — adjusting"})}
                else:
                    yield {"event": "thinking", "data": json.dumps({"step": f"{ev['name']} returned data"})}
            elif kind == "text":
                delta = ev.get("delta") or ""
                full_text_parts.append(delta)
                yield {"event": "text", "data": json.dumps({"delta": delta})}
    except LLMUnavailable as exc:
        err_msg = "The language model is unavailable, so I can't run a multi-source agent query right now."
        msg = DB.add_message(chat_id, "assistant", err_msg, payload={"kind": "error", "detail": str(exc)})
        yield {"event": "error", "data": json.dumps({"message": err_msg, "detail": str(exc)})}
        yield {"event": "done", "data": json.dumps({"message_id": msg["id"], "chat_id": chat_id})}
        return

    full_text = "".join(full_text_parts).strip() or "(no answer)"
    result_payload: dict[str, Any] | None = None
    if collected:
        sql, df, elapsed_ms = collected[-1]
        viz = choose_visualization(question, {}, df)
        result_payload = {
            "title": "Multi-source Result",
            "viz": viz,
            "elapsed_ms": elapsed_ms,
            "sql": sql,
            "how": f"Sources: {', '.join(s['name'] for s in source_summaries[:8])}. Display: {viz}.",
            **_df_to_payload(df),
        }
        yield {"event": "result", "data": json.dumps(result_payload, default=str)}
    elif source_summaries:
        full_text = full_text if full_text != "(no answer)" else "I fetched data, but did not get a final table to show."

    payload: dict[str, Any] = {"kind": "result" if result_payload else "text", "model": "multi-source-agent"}
    if result_payload:
        payload["result"] = result_payload
    msg = DB.add_message(chat_id, "assistant", full_text, payload=payload)
    yield {"event": "done", "data": json.dumps({"message_id": msg["id"], "chat_id": chat_id})}


def _load_history(chat_id: str | None) -> list[dict[str, Any]]:
    if not chat_id:
        return []
    chat = DB.get_chat(chat_id)
    if not chat:
        return []
    return [{"role": m["role"], "content": m["content"]} for m in chat["messages"]]


async def _load_query_sources(
    source_ids: list[str],
    active_row: dict[str, Any] | None,
    *,
    use_active_fallback: bool,
) -> list[tuple[dict[str, Any], DataSource]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source_id in source_ids:
        if source_id == "mcp" or source_id in seen:
            continue
        row = DB.get_source(source_id)
        if row:
            rows.append(row)
            seen.add(source_id)
    if not rows and active_row and use_active_fallback:
        rows.append(active_row)

    loaded: list[tuple[dict[str, Any], DataSource]] = []
    for row in rows:
        source = SOURCES.get(row["id"])
        if source is None:
            source = await _rehydrate_source(row)
            SOURCES[row["id"]] = source
        loaded.append((row, source))
    return loaded


@app.post("/query")
async def query(body: QueryRequest):
    chat_id = body.chat_id or DB.create_chat()["id"]
    llm_router = _router_for_model_mode(body.model_mode)
    model_preset = _model_preset_for_mode(body.model_mode)
    if body.project_id:
        DB.update_chat_project(chat_id, body.project_id)
    chat = DB.get_chat(chat_id)
    if chat and chat.get("project_id"):
        await ensure_project_context(chat["project_id"])

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    active_row = DB.get_active_source()
    pool = get_pool()
    allowed_mcp_ids = _allowed_mcp_connector_ids_for_project(chat.get("project_id") if chat else None)
    has_mcp = any(s.status == "connected" and s.id in allowed_mcp_ids for s in pool.connectors.values())
    requested_source_ids = body.source_ids or []
    selected_mcp = "mcp" in requested_source_ids
    selected_sources = await _load_query_sources(
        requested_source_ids,
        active_row,
        use_active_fallback=not body.source_ids,
    )

    if not selected_sources and not has_mcp:
        raise HTTPException(status_code=400, detail="Attach a source first")

    active_for_legacy = selected_sources[0] if len(selected_sources) == 1 else None
    active_row = active_for_legacy[0] if active_for_legacy else active_row
    source: DataSource | None = active_for_legacy[1] if active_for_legacy else None

    DB.add_message(chat_id, "user", question)
    chat = DB.get_chat(chat_id)
    if chat and (not chat.get("title") or chat["title"] == "New chat"):
        DB.update_chat_title(chat_id, question[:60])

    history = _load_history(chat_id)
    project_instructions: dict[str, Any] | None = None
    source_instructions: dict[str, Any] | None = None
    memory_snippets: list[dict[str, Any]] = []
    if chat and chat.get("project_id"):
        project_instructions = DB.get_project_instructions(chat["project_id"])
        if project_instructions is None:
            project_instructions = get_project_instructions(chat["project_id"])["instructions"]
        DB.rebuild_project_memory(chat["project_id"])
        memory_snippets = DB.search_project_memory(chat["project_id"], question, limit=5)
        notes = DB.list_project_notes(chat["project_id"])[:6]
        if notes:
            note_lines = "\n".join(f"- {n['title']}: {n['content'][:300]}" for n in notes)
            history.append({"role": "project_notes", "content": f"Saved project notes:\n{note_lines}"})
    if active_row:
        source_instructions = _get_or_create_source_instructions(active_row["id"])
    request_id = uuid.uuid4().hex[:12]

    async def event_stream() -> AsyncIterator[dict[str, Any]]:
        loop = asyncio.get_running_loop()

        if selected_sources:
            if len(selected_sources) == 1:
                row, selected_source = selected_sources[0]
                meta_source = {
                    "id": row["id"],
                    "name": row["name"],
                    "kind": row["kind"],
                    "rows": row["rows"],
                }
            else:
                total_rows = sum(int(row.get("rows") or 0) for row, _ in selected_sources)
                meta_source = {
                    "id": "multi",
                    "name": ", ".join(row["name"] for row, _ in selected_sources[:3]) + ("…" if len(selected_sources) > 3 else ""),
                    "kind": "multi",
                    "rows": total_rows,
                }
        elif has_mcp:
            visible_mcp = [s for s in pool.connectors.values() if s.status == "connected" and s.id in allowed_mcp_ids]
            meta_source = {
                "id": None,
                "name": ", ".join(s.name for s in visible_mcp) or "MCP",
                "kind": "mcp",
                "rows": 0,
            }
        else:
            meta_source = {"id": None, "name": "No source", "kind": "none", "rows": 0}
        yield {
            "event": "meta",
            "data": json.dumps({"chat_id": chat_id, "source": meta_source}),
        }
        yield {"event": "thinking", "data": json.dumps({"step": "Reading your question"})}

        if len(selected_sources) > 1 or selected_mcp or (source is None and has_mcp):
            try:
                async for ev in _run_multi_source_agent(chat_id, question, selected_sources, history, request_id, allowed_mcp_ids, llm_router):
                    yield ev
            except Exception as exc:
                log_event(LOGGERS["errors"], "multi_source_agent_error", request_id=request_id, error=str(exc))
                err_msg = "An unexpected error occurred while working across the selected sources."
                DB.add_message(chat_id, "assistant", err_msg, payload={"kind": "error", "detail": str(exc)})
                yield {"event": "error", "data": json.dumps({"message": err_msg, "detail": str(exc)})}
                yield {"event": "done", "data": json.dumps({"chat_id": chat_id})}
            return

        try:
            mcp_summary_text = _build_mcp_summary(pool, allowed_mcp_ids) if has_mcp else ""
            instruction_context = build_instruction_context(
                source_instructions=source_instructions,
                project_instructions=project_instructions,
                memory_snippets=memory_snippets,
                allowed_columns=source.allowed_columns,
                char_budget=3000,
            )
            if llm_router.available:
                intent, model_used = await loop.run_in_executor(
                    None,
                    lambda: llm_router.classify_intent(
                        request_id=request_id,
                        user_question=question,
                        schema_context=source.schema,
                        conversation_summary=conversation_summary(history),
                        mcp_summary=mcp_summary_text,
                        local_source_name=active_row["name"],
                        instruction_context=instruction_context,
                    ),
                )
            else:
                intent, model_used = heuristic_intent(question, source.allowed_columns), "offline-heuristic"
            if model_used != "offline-heuristic":
                model_used = model_preset["model"]
            intent = apply_instruction_rules(
                intent,
                question,
                source.allowed_columns,
                source_instructions=source_instructions,
                project_instructions=project_instructions,
            )

            route = (intent.get("route") or "local").lower()

            # Explicit MCP route — classifier decided the question belongs to a connected MCP source.
            if route == "mcp" and has_mcp:
                async for ev in _run_multi_source_agent(chat_id, question, selected_sources, history, request_id, allowed_mcp_ids, llm_router):
                    yield ev
                return

            # Compound question that needs sequential SQL — route to local agent loop.
            if intent.get("intent_type") == "multi_step" and source is not None:
                async for ev in _run_local_agent(chat_id, question, source, history, request_id, model_used, llm_router):
                    yield ev
                return

            if intent.get("intent_type") == "clarification":
                content = intent.get("clarifying_question") or "Can you clarify the metric or grouping?"
                msg = DB.add_message(chat_id, "assistant", content, payload={"kind": "clarification", "model": model_used})
                yield {"event": "clarify", "data": json.dumps({"content": content, "message_id": msg["id"]})}
                yield {"event": "done", "data": json.dumps({"message_id": msg["id"]})}
                return

            if is_underspecified(intent, question, source.allowed_columns):
                content = underspecified_clarification(source.allowed_columns, active_row["name"])
                msg = DB.add_message(chat_id, "assistant", content, payload={"kind": "clarification", "model": model_used})
                yield {"event": "clarify", "data": json.dumps({"content": content, "message_id": msg["id"]})}
                yield {"event": "done", "data": json.dumps({"message_id": msg["id"], "chat_id": chat_id})}
                return

            if intent.get("intent_type") == "unsupported":
                # Safety net: if the classifier missed the route field but MCP is connected,
                # let the agent try (e.g. user asked about BigQuery while a CSV is active).
                # However, if the user explicitly asked about the "table" or "file" or if the
                # prompt classified it explicitly as 'local' route, don't hallucinate MCP calls.
                if has_mcp and route != "local" and "table" not in question.lower() and "file" not in question.lower():
                    async for ev in _run_mcp_agent(chat_id, question, history, request_id, allowed_mcp_ids, llm_router):
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

            plan = build_query_plan(intent, question, source.allowed_columns)
            validate_readonly_sql(plan.sql)

            filter_count = len(intent.get("filters") or [])
            filter_note = f" · {filter_count} filter{'s' if filter_count != 1 else ''}" if filter_count else ""
            yield {"event": "thinking", "data": json.dumps({"step": f"Understood: {plan.title}{filter_note}"})}
            yield {"event": "thinking", "data": json.dumps({"step": f"Querying {active_row['name']}"})}

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
                    total_plan = build_total_plan(intent, source.allowed_columns, question=question)
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

            if llm_router.available:
                try:
                    chunks_iter = llm_router.summarize_answer_stream(
                        request_id=request_id,
                        user_question=question,
                        intent=intent,
                        result_sample=sample,
                        row_count=len(df),
                        sql=plan.sql,
                        total_row=total_row,
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
