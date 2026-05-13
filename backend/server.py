from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import collections
import collections.abc
import ipaddress
import json
import logging
import math
import os
import re
import secrets
import shutil
import socket
import sys
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import psutil
from opentelemetry import trace
import pandas as pd

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, BackgroundTasks, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

TRACER = trace.get_tracer(__name__)

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


class CloudflareWorkbookDeploy(BaseModel):
    public_base_url: str | None = None
    worker_name: str | None = None


class WorkbookViewUpsert(BaseModel):
    name: str | None = None
    sql: str


class WorkbookViewMerge(BaseModel):
    name: str
    left_table: str
    right_table: str
    left_key: str
    right_key: str
    join_type: str = "inner"


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


class AdminLogin(BaseModel):
    password: str


class TestSuiteCreate(BaseModel):
    name: str
    source_ids: list[str] | None = None
    project_id: str | None = None
    model_mode: str | None = None


class TestQueriesBulk(BaseModel):
    suite_id: str
    queries_text: str | None = None
    queries: list[dict[str, Any]] | None = None


class AutoTestSuiteCreate(BaseModel):
    name: str | None = None
    source_ids: list[str] | None = None
    project_id: str | None = None


class TestRunCreate(BaseModel):
    suite_id: str
    source_ids: list[str] | None = None
    project_id: str | None = None
    model_mode: str | None = None


class FeedbackRequest(BaseModel):
    chat_id: str | None = None
    message_id: str | None = None
    rating: int
    comment: str | None = None
    category: str = "feedback"


class FeedbackStatusUpdate(BaseModel):
    status: str


class TestEvaluationGrade(BaseModel):
    grade: str # 'Pass', 'Fail', 'Partial', 'Error'
    reason: str | None = None


class UserAuth(BaseModel):
    email: str
    password: str


class QueryRequest(BaseModel):
    chat_id: str | None = None
    question: str
    source_ids: list[str] | None = None
    project_id: str | None = None
    model_mode: str | None = None


class ResolvePending(BaseModel):
    upload_id: str
    value: str | list[str]  # sheet name(s), table name, or "direct" / "sql"
    public_base_url: str | None = None


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agents import DomainAgent, get_agent_for_domain
from src.config import AppConfig
from src.travel_orchestrator import TravelOrchestrator
from src.data_sources import (
    DataSource,
    dataframe_to_duckdb_source,
    prepare_api_source,
    prepare_csv_memory_source,
    prepare_csv_source,
    prepare_duckdb_source,
    prepare_excel_source,
    prepare_excel_workbook_duckdb_sources,
    prepare_local_file_source,
    prepare_pdf_source,
)
from src.logging_config import log_event, setup_loggers
from src.mcp_pool import extract_text_content, get_pool, parse_tool_result_to_dataframe
from src.model_router import LLMRouter, LLMUnavailable
from src.prompting import build_answer_prompt, build_local_agent_system_prompt
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
TEST_USER_EMAIL = os.getenv("TEST_USER_EMAIL", "").strip().lower()
TEST_USER_PASSWORD = os.getenv("TEST_USER_PASSWORD", "").strip()


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
JWT_SECRET = os.getenv("JWT_SECRET", "").strip() or API_KEY
USER_AUTH_REQUIRED = os.getenv("USER_AUTH_REQUIRED", "1").strip() != "0" and bool(JWT_SECRET)
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(60 * 60 * 24 * 7)))
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
from src.model_router import setup_phoenix
setup_phoenix(
    api_key=CONFIG.phoenix_api_key,
    project_name=CONFIG.phoenix_project_name,
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "https://app.phoenix.arize.com/v1/traces")
)

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


PUBLIC_PATHS = {"/health", "/auth/login", "/auth/register", "/admin/login"}


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

    # Auto-connect the Duffel MCP bridge if the API token is configured.
    if CONFIG.duffel_api_token:
        duffel_url = os.getenv("DUFFEL_MCP_URL", "http://localhost:8083/sse")
        already_connected = any(
            "duffel" in s.name.lower() for s in pool.connectors.values()
        )
        if not already_connected:
            try:
                cid = await pool.connect(url=duffel_url, name="Duffel Flights")
                state = pool.connectors.get(cid)
                if state:
                    _persist_mcp_state(state, scope="global")
                    logging.info("Duffel MCP bridge connected: %s", duffel_url)
            except Exception as exc:
                logging.warning("Duffel MCP auto-connect failed (start bridge first): %s", exc)

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

from backend.routes.travel_routes import router as travel_router
app.include_router(travel_router)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # CORS preflight is handled by CORSMiddleware before this runs.
    request.state.user_id = "legacy"
    path = request.url.path
    if (
        request.method == "OPTIONS"
        or path in PUBLIC_PATHS
        or path.startswith("/admin/")
        or path.startswith("/mcp/workbooks/")
    ):
        return await call_next(request)
    if not USER_AUTH_REQUIRED or not API_KEY:
        return await call_next(request)
    token = _bearer_token(request)
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Login required"})
    try:
        payload = _decode_access_token(token)
    except ValueError:
        return JSONResponse(status_code=401, content={"detail": "Invalid or expired login"})
    session = DB.get_active_session(str(payload.get("jti") or ""))
    if not session or session["user_id"] != payload.get("sub"):
        return JSONResponse(status_code=401, content={"detail": "Session expired"})
    if session.get("ip_address") and session["ip_address"] != _client_ip(request):
        return JSONResponse(status_code=401, content={"detail": "Session changed networks. Please log in again."})
    request.state.user_id = session["user_id"]
    return await call_next(request)


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    return header.split(" ", 1)[1].strip() or None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign_access_token(payload: dict[str, Any]) -> str:
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT secret is not configured")
    header = {"alg": "HS256", "typ": "JWT"}
    head = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(JWT_SECRET.encode("utf-8"), f"{head}.{body}".encode("ascii"), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64url(sig)}"


def _decode_access_token(token: str) -> dict[str, Any]:
    try:
        head, body, sig = token.split(".", 2)
        expected = hmac.new(JWT_SECRET.encode("utf-8"), f"{head}.{body}".encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url(expected), sig):
            raise ValueError("bad signature")
        payload = json.loads(_b64url_decode(body))
        if float(payload.get("exp", 0)) < time.time():
            raise ValueError("expired")
        if not payload.get("sub") or not payload.get("jti"):
            raise ValueError("missing subject")
        return payload
    except Exception as exc:
        raise ValueError("invalid token") from exc


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 120_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64url(salt)}${_b64url(digest)}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _b64url_decode(salt), int(iterations))
        return hmac.compare_digest(_b64url(candidate), digest)
    except Exception:
        return False


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


def _current_user_id(request: Request) -> str:
    return str(getattr(request.state, "user_id", "legacy") or "legacy")


def _is_test_user(request: Request) -> bool:
    user_id = _current_user_id(request)
    if user_id == "legacy" or not TEST_USER_EMAIL:
        return False
    user = DB.get_user(user_id)
    return bool(user and str(user.get("email", "")).strip().lower() == TEST_USER_EMAIL)


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


def _persist_source(source_id: str, source: DataSource, kind: str, origin: dict[str, Any] | None, owner_id: str = "legacy") -> dict[str, Any]:
    SOURCES[source_id] = source
    DB.upsert_source(
        source_id=source_id,
        name=source.display_name,
        kind=kind,
        rows=source.row_count,
        schema_json=json.dumps(source.schema, default=str),
        origin=origin,
        owner_id=owner_id,
    )
    if DB.get_source_instructions(source_id) is None:
        DB.upsert_source_instructions(source_id, default_source_instructions(source.schema, source.display_name))
    DB.set_active_source(source_id, owner_id=owner_id)
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


def _get_view_type(chat_id: str) -> str:
    chat = DB.get_chat(chat_id)
    if not chat or not chat.get("project_id"):
        return "table"
    project_instructions = DB.get_project_instructions(chat["project_id"])
    if not project_instructions:
        return "table"
    category = project_instructions.get("category")
    if category == "education":
        return "timetable"
    return "table"


def _get_domain_agent(chat_id: str) -> DomainAgent | None:
    chat = DB.get_chat(chat_id)
    if not chat or not chat.get("project_id"):
        return None
    project_instructions = DB.get_project_instructions(chat["project_id"])
    if not project_instructions:
        return None
    category = project_instructions.get("category")
    if not category:
        return None
    return get_agent_for_domain(category)


def _get_domain_prompt(chat_id: str) -> str:
    agent = _get_domain_agent(chat_id)
    return agent.get_system_prompt() if agent else ""


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
    deployment = DB.get_workbook_mcp_deployment(state.id)
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
        "cloudflare": deployment,
    }


def _safe_worker_name(raw: str) -> str:
    name = re.sub(r"[^a-z0-9-]+", "-", raw.lower()).strip("-")
    return (name or "unipro-workbook-mcp")[:63]


def _safe_workbook_view_name(raw: str) -> str:
    name = re.sub(r"[^0-9a-zA-Z_]+", "_", raw.strip()).strip("_").lower()
    if not name:
        raise HTTPException(status_code=400, detail="View name is required")
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$", name):
        raise HTTPException(status_code=400, detail="View name must start with a letter or underscore")
    return name


def _get_workbook_connector_state(connector_id: str) -> Any:
    state = get_pool().connectors.get(connector_id)
    if not state or state.status != "connected" or not hasattr(state, "_excel_connector"):
        raise HTTPException(status_code=404, detail="Workbook MCP connector not found")
    connector = getattr(state, "_excel_connector", None)
    if not connector or not hasattr(connector, "db_path"):
        raise HTTPException(status_code=400, detail="Connector is not a workbook MCP")
    return state


def _refresh_workbook_connector_tools(connector_id: str) -> None:
    state = get_pool().connectors.get(connector_id)
    connector = getattr(state, "_excel_connector", None) if state else None
    if not state or connector is None:
        return
    state.tools = connector.list_tools()
    record = DB.get_mcp_connector(connector_id)
    _persist_mcp_state(state, scope=record.get("scope", "global") if record else "global")


def _preview_workbook_sql(connector_id: str, sql: str) -> tuple[list[str], int]:
    state = _get_workbook_connector_state(connector_id)
    connector = getattr(state, "_excel_connector")
    validate_readonly_sql(sql)
    import duckdb
    con = duckdb.connect(connector.db_path)
    try:
        df = con.execute(f"SELECT * FROM ({sql}) AS view_preview LIMIT 1000").fetchdf()
        count = con.execute(f"SELECT COUNT(*) FROM ({sql}) AS view_count").fetchone()[0]
    finally:
        con.close()
    return [str(c) for c in df.columns], int(count or 0)


def _apply_workbook_view(connector_id: str, name: str, sql: str) -> dict[str, Any]:
    state = _get_workbook_connector_state(connector_id)
    connector = getattr(state, "_excel_connector")
    view_name = _safe_workbook_view_name(name)
    columns, row_count = _preview_workbook_sql(connector_id, sql)
    import duckdb
    con = duckdb.connect(connector.db_path)
    try:
        con.execute(f"CREATE OR REPLACE VIEW {quote_ident(view_name)} AS {sql}")
    finally:
        con.close()
    if view_name not in connector.table_names:
        connector.table_names.append(view_name)
    view = DB.upsert_workbook_view(
        connector_id=connector_id,
        name=view_name,
        sql=sql,
        columns=columns,
        row_count=row_count,
    )
    _refresh_workbook_connector_tools(connector_id)
    return view


def build_cloudflare_workbook_worker() -> str:
    return """
export default {
  async fetch(request, env) {
    if (new URL(request.url).pathname !== "/mcp") {
      return new Response("Not found", { status: 404 });
    }
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }
    const body = await request.text();
    const response = await fetch(env.BACKEND_RPC_URL, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-workbook-mcp-token": env.WORKBOOK_MCP_TOKEN
      },
      body
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "content-type": "application/json" }
    });
  }
};
""".strip()


def deploy_cloudflare_workbook_worker(*, script_name: str, backend_rpc_url: str, public_token: str) -> str:
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    api_key = os.getenv("CLOUDFLARE_API_KEY", "").strip()
    api_email = os.getenv("CLOUDFLARE_API_EMAIL", "").strip()
    if not account_id or not (api_token or (api_key and api_email)):
        raise RuntimeError("Cloudflare credentials are not configured")

    import requests

    headers = {"Authorization": f"Bearer {api_token}"} if api_token else {"X-Auth-Key": api_key, "X-Auth-Email": api_email}
    metadata = {
        "main_module": "worker.js",
        "compatibility_date": "2026-05-01",
        "bindings": [
            {"type": "plain_text", "name": "BACKEND_RPC_URL", "text": backend_rpc_url},
            {"type": "plain_text", "name": "WORKBOOK_MCP_TOKEN", "text": public_token},
        ],
    }
    files = {
        "metadata": ("metadata.json", json.dumps(metadata), "application/json"),
        "worker.js": ("worker.js", build_cloudflare_workbook_worker(), "application/javascript+module"),
    }
    base = f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
    upload = requests.put(f"{base}/workers/scripts/{script_name}", headers=headers, files=files, timeout=30)
    if not upload.ok:
        raise RuntimeError(f"Cloudflare worker upload failed ({upload.status_code})")

    subdomain_resp = requests.get(f"{base}/workers/subdomain", headers=headers, timeout=15)
    if not subdomain_resp.ok:
        raise RuntimeError(f"Cloudflare subdomain lookup failed ({subdomain_resp.status_code})")
    subdomain = (subdomain_resp.json().get("result") or {}).get("subdomain")
    if not subdomain:
        raise RuntimeError("Cloudflare workers.dev subdomain is not configured")

    requests.post(
        f"{base}/workers/scripts/{script_name}/subdomain",
        headers={**headers, "Content-Type": "application/json"},
        json={"enabled": True},
        timeout=15,
    )
    return f"https://{script_name}.{subdomain}.workers.dev/mcp"


async def _deploy_workbook_mcp_cloudflare(connector_id: str, public_base_url: str | None, worker_name: str | None = None) -> dict[str, Any]:
    public_base = (public_base_url or "").rstrip("/")
    if not public_base:
        raise RuntimeError("Public base URL is required")
    safe_worker_name = _safe_worker_name(worker_name or f"unipro-{connector_id}-mcp")
    public_token = secrets.token_urlsafe(32)
    backend_rpc_url = f"{public_base}/mcp/workbooks/{connector_id}/rpc"
    worker_url = await asyncio.to_thread(
        deploy_cloudflare_workbook_worker,
        script_name=safe_worker_name,
        backend_rpc_url=backend_rpc_url,
        public_token=public_token,
    )
    return DB.upsert_workbook_mcp_deployment(
        connector_id=connector_id,
        worker_name=safe_worker_name,
        worker_url=worker_url,
        public_token=public_token,
    )


def _verify_admin(request: Request):
    token = request.headers.get("x-admin-token")
    if not CONFIG.admin_password:
        raise HTTPException(status_code=501, detail="Admin password not configured")

    expected = hashlib.sha256(CONFIG.admin_password.encode()).hexdigest()
    if token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/admin/session")
async def admin_session(request: Request) -> dict[str, Any]:
    _verify_admin(request)
    return {"ok": True, "role": "admin"}


@app.post("/admin/login")
async def admin_login(payload: AdminLogin, request: Request) -> dict[str, Any]:
    if not CONFIG.admin_password:
        raise HTTPException(status_code=501, detail="Admin password not configured on server")
    if payload.password == CONFIG.admin_password:
        # In a real app, we'd use a JWT. For this internal tool, we'll return a simple token
        # derived from the password to keep it stateless and simple.
        admin_token = hashlib.sha256(CONFIG.admin_password.encode()).hexdigest()
        
        # Ensure a system 'Admin' user exists for the regular app part
        admin_email = "admin@unipro.ai"
        user = DB.get_user_by_email(admin_email)
        if not user:
            user = DB.create_user(admin_email, _hash_password(secrets.token_urlsafe(32)))
        
        user_session = _issue_user_token(user, request)
        
        return {
            "token": admin_token,
            "user_token": user_session["access_token"],
            "user": user_session["user"]
        }
    raise HTTPException(status_code=401, detail="Invalid admin password")


@app.get("/admin/stats")
async def admin_stats(request: Request) -> dict[str, Any]:
    _verify_admin(request)

    stats = {
        "top_projects": [],
        "top_sources": [],
        "system_metrics": {
            "total_chats": 0,
            "total_messages": 0,
            "avg_query_latency_ms": 0,
            "avg_llm_latency_ms": 0,
            "avg_faithfulness": None,
            "hallucination_count": 0,
        },
        "system_health": {
            "cpu_percent": psutil.cpu_percent(),
            "ram_percent": psutil.virtual_memory().percent,
            "ram_used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
            "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "disk_percent": psutil.disk_usage("/").percent,
            "disk_free_gb": round(psutil.disk_usage("/").free / (1024**3), 1),
        },
        "openrouter": {
            "limit": None,
            "usage": None,
            "label": "Unknown",
        },
        "config": {
            "phoenix_project_name": CONFIG.phoenix_project_name
        }
    }

    with DB._conn() as con:
        row = con.execute("SELECT COUNT(*) as c FROM chats").fetchone()
        if row: stats["system_metrics"]["total_chats"] = row["c"]

        row = con.execute("SELECT COUNT(*) as c FROM messages").fetchone()
        if row: stats["system_metrics"]["total_messages"] = row["c"]

        # Calculate average faithfulness from hallucination logs
        row = con.execute("SELECT AVG(score) as avg_score, COUNT(*) as cnt FROM hallucination_logs").fetchone()
        if row and row["avg_score"] is not None:
            stats["system_metrics"]["avg_faithfulness"] = round(row["avg_score"] * 100, 1)
        
        # Count hallucinations (score < 0.5)
        row = con.execute("SELECT COUNT(*) as c FROM hallucination_logs WHERE score < 0.5").fetchone()
        if row:
            stats["system_metrics"]["hallucination_count"] = row["c"]

        # Calculate robust latencies from test_evaluations (benchmarks)
        row = con.execute("SELECT AVG(latency_ms) as avg_l FROM test_evaluations WHERE latency_ms IS NOT NULL").fetchone()
        if row and row["avg_l"]:
            stats["system_metrics"]["avg_query_latency_ms"] = int(row["avg_l"])

        # For LLM latency, we look at the last 100 benchmark evaluations
        row = con.execute("SELECT AVG(latency_ms) as avg_l FROM (SELECT latency_ms FROM test_evaluations WHERE latency_ms IS NOT NULL ORDER BY created_at DESC LIMIT 100)").fetchone()
        if row and row["avg_l"]:
            stats["system_metrics"]["avg_llm_latency_ms"] = int(row["avg_l"])

        proj_rows = con.execute('''
            SELECT p.title, COUNT(m.id) as msg_count
            FROM projects p
            JOIN chats c ON c.project_id = p.id
            JOIN messages m ON m.chat_id = c.id
            GROUP BY p.id
            ORDER BY msg_count DESC
            LIMIT 5
        ''').fetchall()
        stats["top_projects"] = [{"name": r["title"], "value": r["msg_count"]} for r in proj_rows]

        src_rows = con.execute('''
            SELECT s.name, COUNT(pf.id) as link_count
            FROM sources s
            JOIN project_files pf ON pf.source_id = s.id
            GROUP BY s.id
            ORDER BY link_count DESC
            LIMIT 5
        ''').fetchall()
        stats["top_sources"] = [{"name": r["name"] or "Unnamed", "value": r["link_count"]} for r in src_rows]

    stats["token_usage_by_project"] = DB.list_token_usage_by_project()
    stats["token_usage_by_purpose"] = DB.list_token_usage_by_purpose()
    stats["query_loop_summary"] = DB.query_loop_summary()

    if CONFIG.openrouter_api_key:
        def fetch_or():
            import urllib.request
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {CONFIG.openrouter_api_key}"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())
        try:
            data = await asyncio.to_thread(fetch_or)
            d = data.get("data", {})
            stats["openrouter"]["limit"] = d.get("limit")
            stats["openrouter"]["usage"] = d.get("usage")
            stats["openrouter"]["label"] = d.get("label", "Key")
        except Exception as e:
            logging.error(f"Failed to fetch OpenRouter stats: {e}")

    return stats


@app.get("/admin/hallucinations")
async def list_hallucinations(request: Request, limit: int = 50):
    _verify_admin(request)
    return DB.list_hallucination_logs(limit=limit)


@app.get("/admin/traces")
async def list_traces(request: Request, limit: int = 100):
    _verify_admin(request)
    with DB._conn() as con:
        rows = con.execute(
            """
            SELECT 
                m.id, 
                m.content as query, 
                m.trace_id, 
                m.created_at as timestamp,
                c.id as chat_id,
                p.title as project_name,
                hl.score as hallucination_score
            FROM messages m
            JOIN chats c ON m.chat_id = c.id
            LEFT JOIN projects p ON c.project_id = p.id
            LEFT JOIN hallucination_logs hl ON hl.message_id = m.id
            WHERE m.role = 'user' AND m.trace_id IS NOT NULL
            ORDER BY m.created_at DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
    
    traces = []
    for r in rows:
        proj = CONFIG.phoenix_project_name
        
        # Determine status based on hallucination score if available
        status = "success"
        score = r["hallucination_score"]
        if score is not None:
            if score < 0.5: status = "hallucination"
            elif score < 0.9: status = "error" # Or "partial/warning"
            
        traces.append({
            "id": r["id"],
            "query": r["query"],
            "trace_id": r["trace_id"],
            "timestamp": r["timestamp"],
            "status": status,
            "phoenix_url": f"https://app.phoenix.arize.com/projects/{proj}/traces/{r['trace_id']}"
        })
    # Calculate summary metrics for the dashboard cards
    avg_faithfulness = None
    hallucination_count = 0
    with DB._conn() as con:
        row = con.execute("SELECT AVG(score) as avg_s FROM hallucination_logs").fetchone()
        if row and row["avg_s"] is not None:
            avg_faithfulness = round(row["avg_s"] * 100, 1)
        
        row = con.execute("SELECT COUNT(*) as c FROM hallucination_logs WHERE score < 0.5").fetchone()
        if row:
            hallucination_count = row["c"]

    return {
        "traces": traces,
        "config": {
            "phoenix_project_name": CONFIG.phoenix_project_name
        },
        "metrics": {
            "avg_faithfulness": avg_faithfulness,
            "hallucination_count": hallucination_count,
            "trace_volume": len(traces)
        }
    }


@app.get("/admin/query-loops")
async def admin_query_loops(request: Request, limit: int = 100) -> dict[str, Any]:
    _verify_admin(request)
    return {
        "summary": DB.query_loop_summary(),
        "queries": DB.list_query_loop_metrics(limit=limit),
    }


@app.get("/admin/user-analytics")
async def user_analytics(request: Request, limit: int = 100):
    _verify_admin(request)
    with DB._conn() as con:
        feedback_rows = con.execute(
            """
            SELECT category, rating, status, COUNT(*) as count
            FROM user_feedback
            GROUP BY category, rating, status
            ORDER BY count DESC
            """
        ).fetchall()
        error_rows = con.execute(
            """
            SELECT m.id, m.chat_id, m.content, m.created_at, c.title as chat_title
            FROM messages m
            JOIN chats c ON c.id = m.chat_id
            WHERE m.payload LIKE '%"kind": "error"%'
            ORDER BY m.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        user_rows = con.execute(
            """
            SELECT content
            FROM messages
            WHERE role = 'user'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        instruction_rows = con.execute(
            "SELECT project_id, instructions_json FROM project_instructions"
        ).fetchall()

    stop_words = {"the", "and", "for", "with", "from", "this", "that", "what", "show", "give", "how", "can", "you", "about", "please"}
    vocab: dict[str, int] = {}
    for row in user_rows:
        for word in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", row["content"].lower()):
            if word not in stop_words:
                vocab[word] = vocab.get(word, 0) + 1

    industry_terms: dict[tuple[str, str], dict[str, Any]] = {}
    for row in instruction_rows:
        try:
            instructions = json.loads(row["instructions_json"] or "{}")
        except Exception:
            continue
        industry = str(instructions.get("category") or "general").strip().lower() or "general"
        for term, meta in (instructions.get("dynamic_vocabulary") or {}).items():
            clean_term = str(term).strip().lower()
            if not clean_term:
                continue
            item = industry_terms.setdefault((industry, clean_term), {"project_ids": set(), "columns": set()})
            item["project_ids"].add(row["project_id"])
            if isinstance(meta, dict):
                item["columns"].update(str(col) for col in meta.get("columns", []) if str(col).strip())

    industry_vocabulary = [
        {
            "industry": industry,
            "term": term,
            "project_count": len(meta["project_ids"]),
            "columns": sorted(meta["columns"]),
        }
        for (industry, term), meta in industry_terms.items()
        if len(meta["project_ids"]) >= 2
    ]
    industry_vocabulary.sort(key=lambda item: (-item["project_count"], item["industry"], item["term"]))

    return {
        "feedback_summary": [dict(r) for r in feedback_rows],
        "recent_errors": [dict(r) for r in error_rows],
        "vocabulary": [
            {"term": term, "count": count}
            for term, count in sorted(vocab.items(), key=lambda item: item[1], reverse=True)[:30]
        ],
        "industry_vocabulary": industry_vocabulary[:30],
        "message_sample_size": len(user_rows),
    }


@app.post("/admin/maintenance/clear-cache")
async def clear_cache_endpoint(request: Request):
    _verify_admin(request)
    freed_mb = 0
    try:
        cache_dir = CONFIG.cache_dir
        if cache_dir.exists():
            # Calculate size before deletion
            total_size = sum(f.stat().st_size for f in cache_dir.glob('**/*') if f.is_file())
            freed_mb = round(total_size / (1024 * 1024), 2)
            
            # Delete contents but keep the folder
            for item in cache_dir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
                    
        return {"status": "success", "freed_mb": freed_mb, "message": f"Cleared {freed_mb}MB from cache."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@app.post("/admin/testing/suites")
async def create_test_suite(payload: TestSuiteCreate, request: Request):
    _verify_admin(request)
    metadata = {
        "source_ids": payload.source_ids or [],
        "project_id": payload.project_id,
        "model_mode": payload.model_mode or "flash",
    }
    return DB.create_test_suite(payload.name, metadata=metadata)


@app.get("/admin/testing/suites")
async def list_test_suites(request: Request):
    _verify_admin(request)
    return DB.list_test_suites()


@app.get("/admin/testing/suites/{suite_id}/queries")
async def list_test_queries(suite_id: str, request: Request):
    _verify_admin(request)
    return DB.list_test_queries(suite_id)


@app.post("/admin/testing/queries/bulk")
async def add_test_queries_bulk(payload: TestQueriesBulk, request: Request):
    _verify_admin(request)
    queries = []
    if payload.queries:
        queries = payload.queries
    elif payload.queries_text:
        lines = [line.strip() for line in payload.queries_text.split("\n") if line.strip()]
        for line in lines:
            if ":" in line and len(line.split(":", 1)[0]) < 30:
                cat, q = line.split(":", 1)
                queries.append({"question": q.strip(), "category": cat.strip()})
            else:
                queries.append({"question": line, "category": "Uncategorized"})
    
    if queries:
        DB.add_test_queries(payload.suite_id, queries)
    return {"count": len(queries)}


def _auto_test_queries_for_source(source: dict[str, Any]) -> list[dict[str, str]]:
    try:
        schema = json.loads(source.get("schema_json") or "{}")
    except json.JSONDecodeError:
        schema = {}
    raw_columns = schema.get("columns") or []
    columns = [c.get("name") if isinstance(c, dict) else str(c) for c in raw_columns]
    columns = [c for c in columns if c]
    source_name = source.get("name") or "this source"
    numeric_hints = [c for c in columns if re.search(r"amount|price|revenue|sales|total|qty|quantity|count|cost|profit", c, re.I)]
    date_hints = [c for c in columns if re.search(r"date|month|year|time|created|updated", c, re.I)]
    category_hints = [c for c in columns if c not in numeric_hints + date_hints][:3]

    queries = [
        {"category": "Source health", "question": f"Summarize the row count and available columns in {source_name}."},
        {"category": "Schema understanding", "question": f"What are the most important business fields in {source_name}?"},
    ]
    if numeric_hints:
        metric = numeric_hints[0]
        queries.append({"category": "Aggregation", "question": f"What is the total {metric} in {source_name}?"})
        if category_hints:
            queries.append({"category": "Breakdown", "question": f"Break down {metric} by {category_hints[0]} in {source_name}."})
    if date_hints and numeric_hints:
        queries.append({"category": "Trend", "question": f"Show the {numeric_hints[0]} trend by {date_hints[0]} in {source_name}."})
    if category_hints:
        queries.append({"category": "Lookup", "question": f"Show a sample of records grouped by {category_hints[0]} in {source_name}."})
    return queries


@app.post("/admin/testing/suites/auto")
async def create_auto_test_suite(payload: AutoTestSuiteCreate, request: Request):
    _verify_admin(request)
    sources: list[dict[str, Any]] = []
    owner_id = _current_user_id(request)
    if payload.source_ids:
        sources = [s for sid in payload.source_ids if (s := (DB.get_source(sid, owner_id=owner_id) or DB.get_source(sid)))]
    elif payload.project_id:
        project = DB.get_project(payload.project_id, owner_id=owner_id) or DB.get_project(payload.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        sources = [
            DB.get_source(f.get("source_id"), owner_id=owner_id) or DB.get_source(f.get("source_id"))
            for f in project.get("files", [])
            if f.get("source_id")
        ]
        sources = [s for s in sources if s]
    else:
        sources = DB.list_sources(owner_id=owner_id)[:3]

    queries: list[dict[str, str]] = []
    for source in sources:
        full_source = DB.get_source(source["id"], owner_id=owner_id) or source
        queries.extend(_auto_test_queries_for_source(full_source))
    if not queries:
        raise HTTPException(status_code=400, detail="No sources available for auto test generation")

    name = payload.name or f"Auto suite {time.strftime('%Y-%m-%d %H:%M')}"
    suite = DB.create_test_suite(
        name,
        metadata={
            "source_ids": [source["id"] for source in sources],
            "project_id": payload.project_id,
            "model_mode": "flash",
        },
    )
    DB.add_test_queries(suite["id"], queries)
    return {**suite, "query_count": len(queries), "queries": queries}


@app.post("/feedback")
async def post_feedback(payload: FeedbackRequest):
    return DB.add_user_feedback(
        chat_id=payload.chat_id,
        message_id=payload.message_id,
        rating=payload.rating,
        comment=payload.comment,
        category=payload.category,
    )


@app.get("/admin/feedback")
async def list_feedback(request: Request, limit: int = 100, status: str | None = None):
    _verify_admin(request)
    return {"items": DB.list_user_feedback(limit=limit, status=status)}


@app.patch("/admin/feedback/{feedback_id}")
async def update_feedback(feedback_id: str, payload: FeedbackStatusUpdate, request: Request):
    _verify_admin(request)
    if payload.status not in {"open", "reviewing", "resolved", "dismissed"}:
        raise HTTPException(status_code=400, detail="Unsupported feedback status")
    DB.update_user_feedback_status(feedback_id, payload.status)
    return {"ok": True}


@app.patch("/admin/testing/evaluations/{evaluation_id}")
async def grade_evaluation(evaluation_id: str, payload: TestEvaluationGrade, request: Request):
    _verify_admin(request)
    DB.update_test_evaluation(evaluation_id, payload.grade, payload.reason)
    
    # If it's a Fail or Error, log it as a hallucination/issue
    if payload.grade in ("Fail", "Error"):
        # We need the chat_id and message_id, but test evaluations might not have them
        # However, we can at least log the failure if it's from a live run.
        # For now, this is a placeholder as test_evaluations link to test_runs, not live chats.
        pass
        
    return {"ok": True}


@app.post("/admin/testing/runs")
async def start_test_run(request: Request, background_tasks: BackgroundTasks, payload: TestRunCreate):
    _verify_admin(request)
    suite_id = payload.suite_id
    suite = DB.get_test_suite(suite_id)
    if not suite:
        raise HTTPException(status_code=404, detail="Test suite not found")
    
    owner_id = _current_user_id(request)
    active_row = DB.get_active_source(owner_id=owner_id)
    suite_metadata = suite.get("metadata") or {}
    source_ids = payload.source_ids or suite_metadata.get("source_ids") or []
    if not source_ids and active_row:
        source_ids = [active_row["id"]]
    snapshot = {
        "model": CONFIG.model,
        "agent_model": CONFIG.agent_model,
        "active_source": active_row["name"] if active_row else None,
        "active_source_id": active_row["id"] if active_row else None,
        "source_ids": source_ids,
        "project_id": payload.project_id if payload.project_id is not None else suite_metadata.get("project_id"),
        "model_mode": payload.model_mode or suite_metadata.get("model_mode") or "flash",
        "owner_id": owner_id,
    }
    run = DB.create_test_run(suite_id, snapshot)
    background_tasks.add_task(run_test_suite_background, run["id"], suite_id, snapshot)
    return run


@app.get("/admin/testing/runs")
async def list_test_runs(request: Request, suite_id: str | None = None):
    _verify_admin(request)
    return DB.list_test_runs(suite_id)


@app.get("/admin/testing/runs/{run_id}/evaluations")
async def list_test_evaluations(run_id: str, request: Request):
    _verify_admin(request)
    evals = DB.list_test_evaluations(run_id)
    return {
        "evaluations": evals,
        "config": {
            "phoenix_project_name": CONFIG.phoenix_project_name
        }
    }


def _internal_test_request(owner_id: str) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/query",
        "headers": [],
        "client": ("127.0.0.1", 0),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope)
    request.state.user_id = owner_id or "legacy"
    return request


def _json_event_data(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"raw": data}
    return {}


def _format_test_answer(answer: str, result_payload: dict[str, Any] | None) -> str:
    clean_answer = answer.strip()
    if not result_payload:
        return clean_answer or "(no answer)"

    if not clean_answer or clean_answer == "(no answer)":
        clean_answer = _result_grounded_answer("", result_payload)

    columns = result_payload.get("columns") or []
    title = result_payload.get("title") or "Result"
    rows = result_payload.get("row_count")
    viz = result_payload.get("viz") or "table"
    summary = f"Result card: {title}; rows={rows}; viz={viz}; columns={', '.join(map(str, columns[:8]))}"
    return f"{clean_answer}\n\n{summary}".strip()


async def _collect_live_test_query(question: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    owner_id = str(snapshot.get("owner_id") or "legacy")
    body = QueryRequest(
        chat_id=None,
        question=question,
        source_ids=snapshot.get("source_ids") or None,
        project_id=snapshot.get("project_id"),
        model_mode=snapshot.get("model_mode") or "flash",
    )
    response = await query_endpoint(body, _internal_test_request(owner_id), BackgroundTasks())

    answer_parts: list[str] = []
    result_payload: dict[str, Any] | None = None
    error_message = ""
    done_payload: dict[str, Any] = {}

    async for item in response.body_iterator:
        if not isinstance(item, dict):
            continue
        event = item.get("event") or "message"
        data = _json_event_data(item.get("data"))
        if event == "text":
            answer_parts.append(str(data.get("delta") or ""))
        elif event == "result":
            result_payload = data
        elif event == "error":
            error_message = str(data.get("message") or data.get("detail") or "Query failed")
        elif event == "done":
            done_payload = data

    latency_ms = (time.time() - started) * 1000
    if error_message:
        return {
            "answer": error_message,
            "latency_ms": latency_ms,
            "grade": "Error",
            "reason": error_message,
            "trace_id": done_payload.get("trace_id"),
        }
    return {
        "answer": _format_test_answer("".join(answer_parts), result_payload),
        "latency_ms": latency_ms,
        "grade": None,
        "reason": None,
        "trace_id": done_payload.get("trace_id"),
    }


async def run_test_suite_background(run_id: str, suite_id: str, snapshot: dict):
    queries = DB.list_test_queries(suite_id)
    for q in queries:
        with TRACER.start_as_current_span("test_query") as span:
            trace_id = format(span.get_span_context().trace_id, '032x')
            span.set_attribute("test_run_id", run_id)
            span.set_attribute("query_id", q["id"])
            span.set_attribute("question", q["question"])
            
            start_time = time.time()
            try:
                result = await _collect_live_test_query(q["question"], snapshot)
                eval_id = DB.add_test_evaluation(
                    run_id,
                    q["id"],
                    result["answer"],
                    result.get("latency_ms") or ((time.time() - start_time) * 1000),
                    grade=result.get("grade"),
                    reason=result.get("reason"),
                    trace_id=result.get("trace_id") or trace_id,
                )
                
                # Trigger AI auto-grading inside this background run.
                if ROUTER.available and result.get("grade") != "Error":
                    from opentelemetry.trace import set_span_in_context
                    bg_context = set_span_in_context(span)
                    await evaluate_test_evaluation_background(
                        eval_id,
                        q["question"],
                        result["answer"],
                        q.get("expected_answer"),
                        parent_context=bg_context
                    )
            except Exception as e:
                logging.error(f"Test run evaluation failed for query {q['id']}: {e}")
                span.record_exception(e)
                DB.add_test_evaluation(run_id, q["id"], f"Error: {str(e)}", (time.time() - start_time) * 1000, grade="Error", trace_id=trace_id)
    DB.update_test_run_progress(run_id, status="completed", completed_at=time.time())


async def evaluate_hallucination_background(chat_id: str, message_id: str, question: str, answer: str, context: str, parent_context: Any = None):
    """LLM-as-a-judge to detect hallucinations (faithfulness)."""
    if not ROUTER.available:
        return
    
    # Propagate trace context if provided
    from opentelemetry.context import attach, detach
    token = None
    if parent_context:
        token = attach(parent_context)
    
    with TRACER.start_as_current_span("faithfulness_judge") as span:
        span.set_attribute("message_id", message_id)
        
        prompt = f"""
Evaluate if the following Answer is faithful to the provided Context.
A faithful answer only contains information present in or logically inferrable from the context.
An unfaithful answer (hallucination) contains information NOT in the context.

Question: {question}
Context: {context}
Answer: {answer}

Respond ONLY in JSON format:
{{
  "score": float, // 1.0 for fully faithful, 0.0 for pure hallucination
  "reason": "short explanation"
}}
"""
        try:
            result, usage = await asyncio.to_thread(ROUTER._generate_json, prompt, f"hal_{message_id}")
            score = float(result.get("score", 1.0))
            reason = result.get("reason", "")
            span.set_attribute("score", score)
            span.set_attribute("reason", reason)
            
            DB.add_hallucination_log(chat_id, message_id, score, reason)
            
            # Also log token usage for the evaluation itself
            chat = DB.get_chat(chat_id)
            DB.add_token_usage(
                project_id=chat.get("project_id") if chat else None,
                user_id=chat.get("owner_id") if chat else None,
                model=ROUTER.model,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                purpose="administrative",
            )
        except Exception as e:
            span.record_exception(e)
            logging.error(f"Hallucination evaluation failed for message {message_id}: {e}")
        finally:
            if token:
                detach(token)


async def evaluate_test_evaluation_background(eval_id: str, question: str, answer: str, expected: str | None, parent_context: Any = None):
    """LLM-as-a-judge to auto-grade benchmark test queries."""
    if not ROUTER.available:
        return
        
    # Propagate trace context if provided
    from opentelemetry.context import attach, detach
    token = None
    if parent_context:
        token = attach(parent_context)
        
    with TRACER.start_as_current_span("benchmark_judge") as span:
        span.set_attribute("eval_id", eval_id)
        
        prompt = f"""
Evaluate if the following AI Answer is correct given the Question and the Expected Answer (if provided).

Question: {question}
Expected Answer (Golden): {expected or "Not provided"}
AI Answer to Evaluate: {answer}

Criteria:
1. 'Pass' if the AI answer is factually correct and matches the core meaning of the expected answer.
2. 'Partial' if it's mostly correct but misses a small detail or formatting.
3. 'Fail' if it's factually wrong or contradicts the expected answer.

Respond ONLY in JSON format:
{{
  "grade": "Pass" | "Partial" | "Fail",
  "reason": "short explanation of why this grade was given"
}}
"""
        try:
            result, usage = await asyncio.to_thread(ROUTER._generate_json, prompt, f"test_eval_{eval_id}")
            grade = result.get("grade", "Fail")
            reason = result.get("reason", "")
            span.set_attribute("ai_grade", grade)
            span.set_attribute("ai_reason", reason)
            
            DB.update_test_evaluation_ai_grade(eval_id, grade, reason)
        except Exception as e:
            span.record_exception(e)
            logging.error(f"Benchmark auto-grading failed for eval {eval_id}: {e}")
        finally:
            if token:
                detach(token)


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


# -- health ----------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _issue_user_token(user: dict[str, Any], request: Request) -> dict[str, Any]:
    now = time.time()
    expires_at = now + SESSION_TTL_SECONDS
    jti = secrets.token_urlsafe(24)
    DB.create_session(
        user_id=user["id"],
        jti=jti,
        ip=_client_ip(request),
        ua=request.headers.get("user-agent"),
        expires_at=expires_at,
    )
    token = _sign_access_token({"sub": user["id"], "email": user["email"], "jti": jti, "iat": now, "exp": expires_at})
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "user": {"id": user["id"], "email": user["email"]},
    }


def _clean_email(email: str) -> str:
    clean = email.strip().lower()
    if not clean or "@" not in clean:
        raise HTTPException(status_code=400, detail="A valid email is required")
    return clean


def _ensure_test_user() -> dict[str, Any] | None:
    if not TEST_USER_EMAIL or not TEST_USER_PASSWORD:
        return None
    password_hash = _hash_password(TEST_USER_PASSWORD)
    user = DB.get_user_by_email(TEST_USER_EMAIL)
    if user:
        DB.update_user_password(user["id"], password_hash)
        return DB.get_user_by_email(TEST_USER_EMAIL)
    return DB.create_user(TEST_USER_EMAIL, password_hash)


@app.post("/auth/register")
def register_user(body: UserAuth, request: Request) -> dict[str, Any]:
    email = _clean_email(body.email)
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if DB.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="An account already exists for this email")
    user = DB.create_user(email, _hash_password(body.password))
    return _issue_user_token(user, request)


@app.post("/auth/login")
def login_user(body: UserAuth, request: Request) -> dict[str, Any]:
    email = _clean_email(body.email)
    if email == TEST_USER_EMAIL:
        _ensure_test_user()
    user = DB.get_user_by_email(email)
    if not user or not _verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _issue_user_token(user, request)


@app.get("/auth/me")
def auth_me(request: Request) -> dict[str, Any]:
    user = DB.get_user(_current_user_id(request))
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return {"user": {"id": user["id"], "email": user["email"]}}


# -- sources ---------------------------------------------------------------
@app.get("/sources")
def list_sources(request: Request, project_id: str | None = None) -> list[dict[str, Any]]:
    owner_id = _current_user_id(request)
    rows = DB.list_sources(owner_id=owner_id)
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

@app.get("/sources/{source_id}/preview")
async def preview_source(source_id: str, request: Request) -> dict[str, Any]:
    row = DB.get_source(source_id, owner_id=_current_user_id(request))
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    source = SOURCES.get(source_id)
    if source is None:
        source = await _rehydrate_source(row)
        SOURCES[source_id] = source
    if source.dataframe is not None:
        df = source.dataframe.head(20).fillna("")
    elif source.db_path:
        import duckdb
        con = _connect_duckdb(source.db_path, read_only=True)
        df = con.execute(f'SELECT * FROM "{source.table_name}" LIMIT 20').fetchdf().fillna("")
        con.close()
    else:
        raise HTTPException(status_code=400, detail="Source not previewable")

    # Format datetime columns to ISO strings
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].astype(str).replace("NaT", "")

    return {
        "name": row["name"],
        "kind": row["kind"],
        "rows": row["rows"],
        "columns": list(df.columns),
        "preview_rows": df.values.tolist(),
        "schema": json.loads(row.get("schema_json") or "[]"),
    }



@app.post("/sources/csv")
def attach_csv(body: AttachCSVPath, request: Request) -> dict[str, Any]:
    try:
        path = Path(body.path).expanduser()
        if body.sql_cache:
            source = prepare_csv_source(path, CONFIG.cache_dir, logger=LOGGERS["cache"], force=False)
            origin = {"type": "csv_sql", "path": str(path)}
        else:
            source = prepare_csv_memory_source(path, logger=LOGGERS["cache"])
            origin = {"type": "csv_memory", "path": str(path)}
        source_id = _make_id()
        return _persist_source(source_id, source, "csv", origin, owner_id=_current_user_id(request))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/sources/excel")
def attach_excel(body: AttachExcelPath, request: Request) -> dict[str, Any]:
    try:
        path = Path(body.path).expanduser()
        source = prepare_excel_source(path, body.sheet, LOGGERS["cache"])
        if body.ingest == "sql" and source.dataframe is not None:
            source = dataframe_to_duckdb_source(source.dataframe, CONFIG.cache_dir, LOGGERS["cache"], path.name, "Excel SQL cache")
        origin = {"type": "excel", "path": str(path), "sheet": body.sheet, "ingest": body.ingest}
        source_id = _make_id()
        return _persist_source(source_id, source, "xlsx", origin, owner_id=_current_user_id(request))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/sources/duckdb")
def attach_duckdb(body: AttachDuckDB, request: Request) -> dict[str, Any]:
    try:
        path = Path(body.path).expanduser()
        source = prepare_duckdb_source(path, body.table, logger=LOGGERS["cache"])
        origin = {"type": "duckdb", "path": str(path), "table": body.table}
        source_id = _make_id()
        return _persist_source(source_id, source, "duckdb", origin, owner_id=_current_user_id(request))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/sources/api")
async def attach_api(body: AttachAPI, request: Request) -> dict[str, Any]:
    await _assert_public_url(body.url)
    try:
        source = await asyncio.to_thread(prepare_api_source, body.url, LOGGERS["cache"], auth_header=body.auth)
        if body.ingest == "sql" and source.dataframe is not None:
            source = await asyncio.to_thread(dataframe_to_duckdb_source, source.dataframe, CONFIG.cache_dir, LOGGERS["cache"], body.url, "API SQL cache")
        origin = {"type": "api", "url": body.url, "auth": body.auth, "ingest": body.ingest}
        source_id = _make_id()
        result = _persist_source(source_id, source, "api", origin, owner_id=_current_user_id(request))
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


def _prepare_archive_pdf_sources(archive_path: Path, extraction_dir: Path, owner_id: str = "legacy") -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
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
            if DB.source_name_exists(source.display_name, owner_id=owner_id):
                raise ValueError(f"{source.display_name} is already attached")
            attached.append(_persist_source(_make_id(), source, "pdf", origin, owner_id=owner_id))
        except Exception as exc:
            skipped.append({"file_name": pdf_path.name, "error": str(exc)})
    if not attached:
        details = "; ".join(f"{item['file_name']}: {item['error']}" for item in skipped[:5])
        raise ValueError(f"No readable PDF tables found in this {_archive_label(archive_path)}. {details}".strip())
    return attached, skipped


def _prepare_zip_pdf_sources(zip_path: Path, extraction_dir: Path, owner_id: str = "legacy") -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    return _prepare_archive_pdf_sources(zip_path, extraction_dir, owner_id=owner_id)


@app.post("/sources/upload")
async def upload_source(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    _cleanup_pending()
    owner_id = _current_user_id(request)
    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")
    try:
        safe_name = _safe_upload_filename(file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if DB.source_name_exists(safe_name, owner_id=owner_id):
        raise HTTPException(status_code=409, detail="A file with this name is already attached")
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
                PENDING[upload_id] = {"path": str(dest), "file_name": file_name, "sheets": sheets, "kind": "xlsx", "owner_id": owner_id, "created_at": time.time()}
                return {"pending": {
                    "kind": "sheet_pick",
                    "upload_id": upload_id,
                    "file_name": file_name,
                    "sheets": sheets,
                    "multi_select": True,
                }}
            sheet = sheets[0] if sheets else None
            source = await asyncio.to_thread(prepare_excel_source, dest, sheet, LOGGERS["cache"])
            origin = {"type": "excel", "path": str(dest), "sheet": sheet, "ingest": "direct"}
            return _source_with_clarifications(_persist_source(_make_id(), source, "xlsx", origin, owner_id=owner_id), source)

        if suffix in {".duckdb", ".db"}:
            tables = await asyncio.to_thread(_list_duckdb_tables, dest)
            if len(tables) > 1:
                PENDING[upload_id] = {"path": str(dest), "file_name": file_name, "tables": tables, "kind": "duckdb", "owner_id": owner_id, "created_at": time.time()}
                return {"pending": {
                    "kind": "table_pick",
                    "upload_id": upload_id,
                    "file_name": file_name,
                    "tables": tables,
                }}
            table = tables[0] if tables else "orders"
            source = await asyncio.to_thread(prepare_duckdb_source, dest, table, LOGGERS["cache"])
            origin = {"type": "duckdb", "path": str(dest), "table": table}
            return _source_with_clarifications(_persist_source(_make_id(), source, "duckdb", origin, owner_id=owner_id), source)

        if suffix == ".csv":
            if size_mb > 100:
                PENDING[upload_id] = {"path": str(dest), "file_name": file_name, "size_mb": size_mb, "kind": "csv", "owner_id": owner_id, "created_at": time.time()}
                return {"pending": {
                    "kind": "ingest_pick",
                    "upload_id": upload_id,
                    "file_name": file_name,
                    "size_mb": size_mb,
                }}
            source = await asyncio.to_thread(prepare_csv_memory_source, dest, LOGGERS["cache"])
            origin = {"type": "csv_memory", "path": str(dest)}
            return _source_with_clarifications(_persist_source(_make_id(), source, "csv", origin, owner_id=owner_id), source)

        if suffix == ".json":
            from src.data_sources import prepare_local_file_source

            source = await asyncio.to_thread(
                prepare_local_file_source,
                dest, CONFIG.cache_dir, LOGGERS["cache"], "orders", None, False, "direct",
            )
            origin = {"type": "json", "path": str(dest)}
            return _source_with_clarifications(_persist_source(_make_id(), source, "json", origin, owner_id=owner_id), source)

        if suffix == ".pdf":
            source = await asyncio.to_thread(prepare_pdf_source, dest, LOGGERS["cache"])
            origin = {"type": "pdf", "path": str(dest)}
            return _source_with_clarifications(_persist_source(_make_id(), source, "pdf", origin, owner_id=owner_id), source)

        if suffix in {".zip", ".7z"}:
            sources, skipped = await asyncio.to_thread(_prepare_archive_pdf_sources, dest, upload_dir / "unpacked", owner_id)
            return {"sources": sources, "skipped": skipped}

        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/sources/resolve_pending")
async def resolve_pending(body: ResolvePending, request: Request) -> dict[str, Any]:
    record = PENDING.get(body.upload_id)
    if not record:
        raise HTTPException(status_code=404, detail="Pending upload not found or already resolved")
    owner_id = _current_user_id(request)
    if record.get("owner_id") and record["owner_id"] != owner_id:
        raise HTTPException(status_code=404, detail="Pending upload not found or already resolved")
    path = Path(record["path"])
    try:
        if record["kind"] == "xlsx":
            if isinstance(body.value, list):
                sources = prepare_excel_workbook_duckdb_sources(path, body.value, CONFIG.cache_dir, LOGGERS["cache"])
                persisted = []
                for source, sheet in zip(sources, body.value):
                    origin = {
                        "type": "duckdb",
                        "path": source.db_path,
                        "table": source.table_name,
                        "source_excel_path": str(path),
                        "sheet": sheet,
                    }
                    persisted.append(_source_with_clarifications(_persist_source(_make_id(), source, "xlsx", origin, owner_id=owner_id), source))
                cid = await get_pool().connect_excel_workbook(
                    db_path=sources[0].db_path or "",
                    table_names=[source.table_name for source in sources],
                    display_name=path.name,
                    dedup_key=f"excel-workbook::{path.resolve()}::{path.stat().st_mtime_ns}::{json.dumps(body.value)}",
                )
                state = get_pool().connectors[cid]
                _persist_mcp_state(state, scope="global")
                DB.upsert_workbook_mcp_metadata(
                    connector_id=cid,
                    db_path=sources[0].db_path or "",
                    table_names=[source.table_name for source in sources],
                    display_name=path.name,
                )
                connector = _serialize_mcp_connector(state)
                deploy_error = None
                if body.public_base_url:
                    try:
                        connector["cloudflare"] = await _deploy_workbook_mcp_cloudflare(cid, body.public_base_url)
                    except Exception as exc:
                        deploy_error = str(exc)
                        connector["cloudflare_error"] = deploy_error
                result = {"sources": persisted, "mcp_connector": connector}
                if deploy_error:
                    result["mcp_deploy_error"] = deploy_error
            else:
                source = prepare_excel_source(path, body.value, LOGGERS["cache"])
                origin = {"type": "excel", "path": str(path), "sheet": body.value, "ingest": "direct"}
                result = _source_with_clarifications(_persist_source(_make_id(), source, "xlsx", origin, owner_id=owner_id), source)
        elif record["kind"] == "duckdb":
            if not isinstance(body.value, str):
                raise HTTPException(status_code=400, detail="Pick one table")
            source = prepare_duckdb_source(path, body.value, logger=LOGGERS["cache"])
            origin = {"type": "duckdb", "path": str(path), "table": body.value}
            result = _source_with_clarifications(_persist_source(_make_id(), source, "duckdb", origin, owner_id=owner_id), source)
        elif record["kind"] == "csv":
            if not isinstance(body.value, str):
                raise HTTPException(status_code=400, detail="Pick one ingest mode")
            ingest = body.value if body.value in ("direct", "sql") else "direct"
            if ingest == "sql":
                source = prepare_csv_source(path, CONFIG.cache_dir, logger=LOGGERS["cache"], force=False)
            else:
                source = prepare_csv_memory_source(path, logger=LOGGERS["cache"])
            origin = {"type": f"csv_{ingest}", "path": str(path)}
            result = _source_with_clarifications(_persist_source(_make_id(), source, "csv", origin, owner_id=owner_id), source)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown pending kind: {record['kind']}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    PENDING.pop(body.upload_id, None)
    return result


@app.delete("/sources/{source_id}")
def delete_source(source_id: str, request: Request) -> dict[str, Any]:
    DB.delete_source(source_id, owner_id=_current_user_id(request))
    SOURCES.pop(source_id, None)
    return {"ok": True}


@app.post("/sources/{source_id}/activate")
def activate_source(source_id: str, request: Request) -> dict[str, Any]:
    if not DB.get_source(source_id, owner_id=_current_user_id(request)):
        raise HTTPException(status_code=404, detail="Source not found")
    DB.set_active_source(source_id, owner_id=_current_user_id(request))
    return {"ok": True}


@app.get("/sources/{source_id}/instructions")
def get_source_instructions(source_id: str, request: Request) -> dict[str, Any]:
    row = DB.get_source(source_id, owner_id=_current_user_id(request))
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    instructions = _get_or_create_source_instructions(source_id)
    return {"source_id": source_id, "instructions": instructions}


@app.patch("/sources/{source_id}/instructions")
def update_source_instructions(source_id: str, body: InstructionsUpdate, request: Request) -> dict[str, Any]:
    row = DB.get_source(source_id, owner_id=_current_user_id(request))
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    normalized = normalize_instructions(body.instructions, _source_allowed_columns_from_row(row))
    return DB.upsert_source_instructions(source_id, normalized)


@app.post("/sources/{source_id}/clarifications")
def apply_source_clarifications(source_id: str, body: SourceClarificationUpdate, request: Request) -> dict[str, Any]:
    row = DB.get_source(source_id, owner_id=_current_user_id(request))
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    allowed = _source_allowed_columns_from_row(row)
    instructions = _get_or_create_source_instructions(source_id)
    answers = body.answers or {}
    if answers.get("row_grain"):
        instructions["row_grain"] = str(answers["row_grain"])
    normalized = normalize_instructions(instructions, allowed)
    return DB.upsert_source_instructions(source_id, normalized)


VOCAB_STOP_WORDS = {
    "the", "and", "for", "with", "from", "this", "that", "what", "show", "give", "how",
    "can", "you", "about", "please", "tell", "need", "want", "all", "are", "was", "were",
    "have", "has", "into", "over", "under", "when", "where", "which", "should", "would",
}


def _learn_project_vocabulary(project_id: str, owner_id: str, question: str) -> None:
    project = DB.get_project(project_id, owner_id=owner_id)
    if not project:
        return

    source_rows = [DB.get_source(f.get("source_id"), owner_id=owner_id) for f in project.get("files", []) if f.get("source_id")]
    clean_rows = [row for row in source_rows if row]
    instructions = DB.get_project_instructions(project_id) or {"category": "general", "notes": "", "metrics": {}, "entities": {}}
    detected_category = detect_project_category(project, clean_rows)
    if detected_category != "general" and instructions.get("category") in {None, "", "general"}:
        instructions["category"] = detected_category

    columns: set[str] = set()
    for row in clean_rows:
        columns.update(_source_allowed_columns_from_row(row))

    dynamic = dict(instructions.get("dynamic_vocabulary") or {})
    for term in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", question.lower()):
        if term in VOCAB_STOP_WORDS:
            continue
        matched_columns = sorted(
            column for column in columns
            if term == column.lower() or term in column.lower().split("_")
        )
        if not matched_columns and len(term) < 4:
            continue
        entry = dict(dynamic.get(term) or {})
        entry["count"] = min(int(entry.get("count") or 0) + 1, 1000)
        if matched_columns:
            entry["columns"] = matched_columns[:5]
        dynamic[term] = entry

    if len(dynamic) > 40:
        dynamic = dict(sorted(dynamic.items(), key=lambda item: int(item[1].get("count") or 0), reverse=True)[:40])
    instructions["dynamic_vocabulary"] = dynamic
    DB.upsert_project_instructions(project_id, instructions)
    DB.rebuild_project_memory(project_id)


# -- chats -----------------------------------------------------------------
@app.get("/chats")
def list_chats(request: Request, project_id: str | None = None) -> list[dict[str, Any]]:
    return DB.list_chats(
        project_id=project_id,
        owner_id=_current_user_id(request),
        include_legacy=_is_test_user(request),
    )


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
async def get_chat(chat_id: str, request: Request) -> dict[str, Any]:
    owner_id = _current_user_id(request)
    chat = DB.get_chat(chat_id, owner_id=owner_id, include_legacy=_is_test_user(request))
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.get("project_id"):
        await ensure_project_context(chat["project_id"])

    # Derive the ordered, deduplicated list of source IDs used in this chat
    # by scanning user message payloads (stored since query endpoint was updated).
    seen_ids: list[str] = []
    seen_set: set[str] = set()
    for m in chat.get("messages", []):
        if m.get("role") == "user":
            payload = m.get("payload") or {}
            for sid in payload.get("source_ids") or []:
                if sid and sid not in seen_set:
                    seen_set.add(sid)
                    seen_ids.append(sid)
    # Resolve source metadata so the frontend can show names without extra fetches
    sources_meta: list[dict[str, Any]] = []
    for sid in seen_ids:
        row = DB.get_source(sid)
        if row:
            sources_meta.append({"id": row["id"], "name": row["name"], "kind": row["kind"], "rows": row.get("rows", 0)})
    chat["source_ids"] = seen_ids
    chat["sources"] = sources_meta
    return chat


@app.post("/chats")
def create_chat(request: Request) -> dict[str, Any]:
    return DB.create_chat(owner_id=_current_user_id(request))


@app.delete("/chats/{chat_id}")
def delete_chat(chat_id: str, request: Request) -> dict[str, Any]:
    DB.delete_chat(chat_id, owner_id=_current_user_id(request))
    return {"ok": True}


@app.patch("/chats/{chat_id}/project")
def update_chat_project(chat_id: str, body: ChatUpdateProject, request: Request) -> dict[str, Any]:
    owner_id = _current_user_id(request)
    if not DB.get_chat(chat_id, owner_id=owner_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    if body.project_id and not DB.get_project(body.project_id, owner_id=owner_id):
        raise HTTPException(status_code=404, detail="Project not found")
    DB.update_chat_project(chat_id, body.project_id, owner_id=owner_id)
    return {"ok": True}


# -- projects --------------------------------------------------------------
@app.get("/projects")
def list_projects(request: Request) -> list[dict[str, Any]]:
    return DB.list_projects(owner_id=_current_user_id(request))


@app.post("/projects")
def create_project(body: ProjectCreate, request: Request) -> dict[str, Any]:
    try:
        return DB.create_project(body.title, owner_id=_current_user_id(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/projects/{project_id}")
def get_project(project_id: str, request: Request) -> dict[str, Any]:
    p = DB.get_project(project_id, owner_id=_current_user_id(request))
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@app.patch("/projects/{project_id}")
def update_project(project_id: str, body: ProjectUpdate, request: Request) -> dict[str, Any]:
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Project title is required")
    try:
        p = DB.update_project(project_id, title, owner_id=_current_user_id(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@app.delete("/projects/{project_id}")
def delete_project(project_id: str, request: Request) -> dict[str, Any]:
    DB.delete_project(project_id, owner_id=_current_user_id(request))
    return {"ok": True}


@app.get("/projects/{project_id}/instructions")
def get_project_instructions(project_id: str, request: Request) -> dict[str, Any]:
    owner_id = _current_user_id(request)
    project = DB.get_project(project_id, owner_id=owner_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    instructions = DB.get_project_instructions(project_id)
    if instructions is None:
        source_rows = [DB.get_source(f.get("source_id"), owner_id=owner_id) for f in project.get("files", []) if f.get("source_id")]
        instructions = {"category": detect_project_category(project, [r for r in source_rows if r]), "notes": "", "metrics": {}, "entities": {}}
        DB.upsert_project_instructions(project_id, instructions)
    return {"project_id": project_id, "instructions": instructions}


@app.patch("/projects/{project_id}/instructions")
def update_project_instructions(project_id: str, body: InstructionsUpdate, request: Request) -> dict[str, Any]:
    if not DB.get_project(project_id, owner_id=_current_user_id(request)):
        raise HTTPException(status_code=404, detail="Project not found")
    instructions = dict(body.instructions or {})
    category = str(instructions.get("category") or "").strip().lower()
    from src.agents import DOMAIN_AGENTS
    allowed_categories = {"general", "sales", "finance", "inventory", "operations", "customer_support"} | set(DOMAIN_AGENTS.keys())
    if category and category not in allowed_categories:
        instructions["category"] = "general"
    return DB.upsert_project_instructions(project_id, instructions)


@app.post("/projects/{project_id}/profile/rebuild")
def rebuild_project_profile(project_id: str, request: Request) -> dict[str, Any]:
    owner_id = _current_user_id(request)
    project = DB.get_project(project_id, owner_id=owner_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    existing = DB.get_project_instructions(project_id) or {}
    source_rows = [DB.get_source(f.get("source_id"), owner_id=owner_id) for f in project.get("files", []) if f.get("source_id")]
    new_category = detect_project_category(project, [r for r in source_rows if r])
    if new_category != "general" or not existing.get("category"):
        existing["category"] = new_category
    saved = DB.upsert_project_instructions(project_id, existing)
    DB.rebuild_project_memory(project_id)
    return saved


@app.post("/projects/{project_id}/files")
def add_project_file(project_id: str, body: ProjectAddFile, request: Request) -> dict[str, Any]:
    owner_id = _current_user_id(request)
    if not DB.get_project(project_id, owner_id=owner_id):
        raise HTTPException(status_code=404, detail="Project not found")
    if body.source_id:
        # Check if source exists
        s = DB.get_source(body.source_id, owner_id=owner_id)
        if not s:
            raise HTTPException(status_code=404, detail="Source not found")
        try:
            res = DB.add_file_to_project(project_id, None, source_id=body.source_id, sheet_name=body.sheet)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    else:
        if not body.file_path:
            raise HTTPException(status_code=400, detail="file_path or source_id required")

        path = Path(body.file_path).expanduser()
        if not path.exists():
            raise HTTPException(status_code=400, detail="File not found")
        try:
            res = DB.add_file_to_project(project_id, str(path), sheet_name=body.sheet)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))


    # Auto-profile after adding a file
    try:
        project = DB.get_project(project_id, owner_id=owner_id)
        if project:
            instructions = DB.get_project_instructions(project_id) or {"category": "general", "notes": "", "metrics": {}, "entities": {}}
            source_rows = [DB.get_source(f.get("source_id"), owner_id=owner_id) for f in project.get("files", []) if f.get("source_id")]
            new_cat = detect_project_category(project, [r for r in source_rows if r])
            if new_cat != "general" and instructions.get("category") == "general":
                instructions["category"] = new_cat
                DB.upsert_project_instructions(project_id, instructions)
    except Exception as exc:
        logging.warning(f"Failed to auto-profile project {project_id}: {exc}")

    return res


@app.delete("/projects/{project_id}/files/{file_id}")
def delete_project_file(project_id: str, file_id: str, request: Request) -> dict[str, Any]:
    if not DB.get_project(project_id, owner_id=_current_user_id(request)):
        raise HTTPException(status_code=404, detail="Project not found")
    DB.remove_file_from_project(project_id, file_id)
    return {"ok": True}


@app.get("/projects/{project_id}/notes")
def list_project_notes(project_id: str, request: Request) -> list[dict[str, Any]]:
    if not DB.get_project(project_id, owner_id=_current_user_id(request)):
        raise HTTPException(status_code=404, detail="Project not found")
    return DB.list_project_notes(project_id)


@app.post("/projects/{project_id}/notes")
def create_project_note(project_id: str, body: ProjectNoteCreate, request: Request) -> dict[str, Any]:
    if not DB.get_project(project_id, owner_id=_current_user_id(request)):
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
def delete_project_note(project_id: str, note_id: str, request: Request) -> dict[str, Any]:
    if not DB.get_project(project_id, owner_id=_current_user_id(request)):
        raise HTTPException(status_code=404, detail="Project not found")
    DB.delete_project_note(project_id, note_id)
    return {"ok": True}


@app.get("/projects/{project_id}/mcp")
def list_project_mcp(project_id: str, request: Request) -> list[dict[str, Any]]:
    if not DB.get_project(project_id, owner_id=_current_user_id(request)):
        raise HTTPException(status_code=404, detail="Project not found")
    return DB.list_project_mcp_connectors(project_id)


@app.post("/projects/{project_id}/mcp/{connector_id}")
def bind_project_mcp(project_id: str, connector_id: str, request: Request) -> dict[str, Any]:
    if not DB.get_project(project_id, owner_id=_current_user_id(request)):
        raise HTTPException(status_code=404, detail="Project not found")
    if not DB.get_mcp_connector(connector_id):
        raise HTTPException(status_code=404, detail="MCP connector not found")
    DB.bind_mcp_to_project(project_id, connector_id)
    return {"ok": True}


@app.delete("/projects/{project_id}/mcp/{connector_id}")
def unbind_project_mcp(project_id: str, connector_id: str, request: Request) -> dict[str, Any]:
    if not DB.get_project(project_id, owner_id=_current_user_id(request)):
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


@app.post("/mcp/workbooks/{connector_id}/rpc")
async def workbook_mcp_rpc(connector_id: str, request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    token = request.headers.get("x-workbook-mcp-token", "")
    if not token or not DB.verify_workbook_mcp_token(connector_id, token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    state = _get_workbook_connector_state(connector_id)
    method = payload.get("method")
    rpc_id = payload.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": state.name, "version": "1.0.0"},
                "capabilities": {"tools": {}},
            },
        }
    if method == "notifications/initialized":
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {"tools": state.tools}}
    if method == "tools/call":
        params = payload.get("params") or {}
        tool_name = params.get("name")
        if not isinstance(tool_name, str):
            raise HTTPException(status_code=400, detail="tools/call requires params.name")
        result = await get_pool().call_tool(connector_id, tool_name, params.get("arguments") or {})
        text = extract_text_content(result)
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"content": [{"type": "text", "text": text}]},
        }
    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


@app.post("/mcp/connectors/{connector_id}/cloudflare")
async def deploy_workbook_mcp_to_cloudflare(connector_id: str, request: Request, body: CloudflareWorkbookDeploy) -> dict[str, Any]:
    _verify_admin(request)
    _get_workbook_connector_state(connector_id)
    return await _deploy_workbook_mcp_cloudflare(connector_id, body.public_base_url or str(request.base_url), body.worker_name)


@app.get("/mcp/connectors/{connector_id}/views")
def list_workbook_views(connector_id: str) -> list[dict[str, Any]]:
    _get_workbook_connector_state(connector_id)
    return DB.list_workbook_views(connector_id)


@app.post("/mcp/connectors/{connector_id}/views")
def create_workbook_view(connector_id: str, body: WorkbookViewUpsert) -> dict[str, Any]:
    name = body.name or "custom_view"
    return _apply_workbook_view(connector_id, name, body.sql.strip())


@app.patch("/mcp/connectors/{connector_id}/views/{view_name}")
def update_workbook_view(connector_id: str, view_name: str, body: WorkbookViewUpsert) -> dict[str, Any]:
    existing = DB.get_workbook_view(connector_id, _safe_workbook_view_name(view_name))
    if not existing:
        raise HTTPException(status_code=404, detail="Workbook view not found")
    return _apply_workbook_view(connector_id, view_name, body.sql.strip())


@app.delete("/mcp/connectors/{connector_id}/views/{view_name}")
def delete_workbook_view(connector_id: str, view_name: str) -> dict[str, Any]:
    state = _get_workbook_connector_state(connector_id)
    connector = getattr(state, "_excel_connector")
    safe_name = _safe_workbook_view_name(view_name)
    import duckdb
    con = duckdb.connect(connector.db_path)
    try:
        con.execute(f"DROP VIEW IF EXISTS {quote_ident(safe_name)}")
    finally:
        con.close()
    connector.table_names = [t for t in connector.table_names if t != safe_name]
    DB.delete_workbook_view(connector_id, safe_name)
    _refresh_workbook_connector_tools(connector_id)
    return {"ok": True}


@app.post("/mcp/connectors/{connector_id}/views/merge")
def merge_workbook_view(connector_id: str, body: WorkbookViewMerge) -> dict[str, Any]:
    join_type = body.join_type.lower().strip()
    if join_type not in {"inner", "left", "right", "full"}:
        raise HTTPException(status_code=400, detail="Join type must be inner, left, right, or full")
    name = _safe_workbook_view_name(body.name)
    left = _safe_workbook_view_name(body.left_table)
    right = _safe_workbook_view_name(body.right_table)
    left_key = _safe_workbook_view_name(body.left_key)
    right_key = _safe_workbook_view_name(body.right_key)
    sql = (
        f"SELECT * FROM {quote_ident(left)} "
        f"{join_type.upper()} JOIN {quote_ident(right)} "
        f"ON {quote_ident(left)}.{quote_ident(left_key)} = {quote_ident(right)}.{quote_ident(right_key)}"
    )
    return _apply_workbook_view(connector_id, name, sql)


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
def _clean_column_name(name: str) -> str:
    name = str(name).strip()

    # 1. If it has an explicit 'AS alias' or 'AS "alias"' or 'as alias', extract it.
    match = re.search(r'\b[aA][sS]\s+["\']?([^"\']+)["\']?$', name)
    if match:
        return match.group(1)

    # 2. If it's a raw SQL expression (contains parenthesis and capitals like MAX, CASE)
    # clean it up. For example, "MAX(CASE WHEN slot_order=1 THEN class END)"
    if "(" in name and ")" in name and re.search(r'\b[A-Z]{3,}\b', name):
        # Remove common SQL keywords/functions to derive a readable header
        cleaned = re.sub(r'\b(MAX|MIN|SUM|AVG|COUNT|COALESCE|CASE|WHEN|THEN|END|ELSE|CAST|TRY_CAST|EXTRACT|FROM|AS)\b', '', name, flags=re.IGNORECASE)
        # Remove punctuation
        cleaned = re.sub(r'[\(\)\[\]\',=]', ' ', cleaned)
        # Remove basic operators
        cleaned = re.sub(r'[-+*/<>|]', ' ', cleaned)
        # Normalize whitespace and title case
        cleaned = re.sub(r'[\s_]+', ' ', cleaned).strip().title()
        if cleaned:
            return cleaned

    return name


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
        "columns": [_clean_column_name(c) for c in df.columns],
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


class _DSMLStreamFilter:
    _START = "<｜｜DSML"
    _END = "</｜｜DSML｜｜tool_calls>"

    def __init__(self) -> None:
        self._buffer = ""
        self._in_dsml = False

    @staticmethod
    def _held_prefix_len(text: str, marker: str) -> int:
        max_len = min(len(text), len(marker) - 1)
        for size in range(max_len, 0, -1):
            if marker.startswith(text[-size:]):
                return size
        return 0

    def feed(self, chunk: str) -> str:
        self._buffer += chunk
        visible: list[str] = []
        while self._buffer:
            if self._in_dsml:
                end_idx = self._buffer.find(self._END)
                if end_idx < 0:
                    keep = self._held_prefix_len(self._buffer, self._END)
                    self._buffer = self._buffer[-keep:] if keep else ""
                    return "".join(visible)
                self._buffer = self._buffer[end_idx + len(self._END):]
                self._in_dsml = False
                continue

            start_idx = self._buffer.find(self._START)
            if start_idx >= 0:
                visible.append(self._buffer[:start_idx])
                self._buffer = self._buffer[start_idx:]
                self._in_dsml = True
                continue

            keep = self._held_prefix_len(self._buffer, self._START)
            if keep:
                visible.append(self._buffer[:-keep])
                self._buffer = self._buffer[-keep:]
            else:
                visible.append(self._buffer)
                self._buffer = ""
            return "".join(visible)
        return "".join(visible)

    def finish(self) -> str:
        if self._in_dsml:
            self._buffer = ""
            self._in_dsml = False
            return ""
        tail = self._buffer
        self._buffer = ""
        return tail


def _sanitize_assistant_text(text: str) -> str:
    stream_filter = _DSMLStreamFilter()
    text = stream_filter.feed(text) + stream_filter.finish()
    text = re.sub(r"<｜｜DSML.*?</｜｜DSML｜｜tool_calls>", "", text, flags=re.DOTALL)
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


def _finalize_visible_answer(raw_text: str, question: str, result_payload: dict[str, Any] | None = None) -> str:
    text = _sanitize_assistant_text(raw_text)
    if text and text != "(no answer)":
        return text
    if result_payload:
        grounded = _result_grounded_answer(question, result_payload)
        if grounded:
            return grounded
    return text or "(no answer)"


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
    with TRACER.start_as_current_span("duckdb_execute") as span:
        span.set_attribute("plan_title", plan.title)
        import duckdb

        start = time.perf_counter()
        try:
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
        except Exception as exc:
            span.record_exception(exc)
            raise
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            span.set_attribute("elapsed_ms", elapsed_ms)
            if 'df' in locals():
                span.set_attribute("row_count", len(df))

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


def _workspace_prompt(source_summaries: list[dict[str, Any]], connector_summary: str, join_candidates: list[dict[str, Any]], domain_prompt: str = "") -> str:
    source_lines: list[str] = []
    for src in source_summaries:
        cols = ", ".join(f"{c['name']}:{c['type']}" for c in src.get("columns", [])[:40])
        source_lines.append(f"- {src['name']} as table {src['table']} ({src['rows']} rows): {cols}")
    join_lines = [
        f"- {c['left_table']}.{c['left_column']} = {c['right_table']}.{c['right_column']} (confidence {c['confidence']:.2f})"
        for c in join_candidates[:10]
    ]
    base_prompt = f"""You are a multi-source data analyst. Use tools to retrieve data and run DuckDB SQL.

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
    if domain_prompt:
        return f"{domain_prompt}\n\n{base_prompt}"
    return base_prompt


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
    user_message_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    span = TRACER.start_span("mcp_agent")
    span.set_attribute("question", question)
    try:
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
        stream_filter = _DSMLStreamFilter()
        loop_metrics = {"round_count": 0, "tool_call_count": 0, "tool_error_count": 0, "thinking_event_count": 0}
        last_tool_call: dict[str, Any] | None = None
        agent = _get_domain_agent(chat_id)
        domain_prompt = agent.get_system_prompt() if agent else ""
        domain_tools = agent.get_tools() if agent else []

        # Merge domain tools into the specs if any
        final_specs = specs + domain_tools

        try:
            async for ev in router.agent_loop_stream(
                request_id=request_id,
                user_question=question,
                conversation_summary=conversation_summary(history),
                tool_specs=final_specs,
                connector_summary=connector_summary,
                on_tool_call=on_tool_call,
                system_prompt=f"{domain_prompt}\n\n{build_mcp_agent_system_prompt(connector_summary)}" if domain_prompt else None,
            ):
                kind = ev["kind"]
                if kind == "tool_call":
                    loop_metrics["tool_call_count"] += 1
                    loop_metrics["thinking_event_count"] += 1
                    loop_metrics["round_count"] = max(loop_metrics["round_count"], int(ev.get("round") or 0) + 1)
                    last_tool_call = ev
                    connector_id = routing.get(ev["name"])
                    cname = name_lookup.get(connector_id, "MCP")
                    args_str = ", ".join(f"{k}={v!r}" for k, v in (ev.get("args") or {}).items())
                    step = f"Calling {ev['name']}({args_str}) on {cname}"
                    yield {"event": "thinking", "data": json.dumps({"step": step})}
                elif kind == "tool_result":
                    loop_metrics["thinking_event_count"] += 1
                    if ev.get("error"):
                        loop_metrics["tool_error_count"] += 1
                        yield {"event": "thinking", "data": json.dumps({"step": f"{ev['name']} returned an error"})}
                    else:
                        yield {"event": "thinking", "data": json.dumps({"step": f"{ev['name']} returned data"})}
                elif kind == "text":
                    delta = ev.get("delta") or ""
                    full_text_parts.append(delta)
                    visible_delta = stream_filter.feed(delta)
                    if visible_delta:
                        yield {"event": "text", "data": json.dumps({"delta": visible_delta})}
        except LLMUnavailable as exc:
            err_text = "All language models are unavailable right now. Try again in a moment."
            msg = DB.add_message(chat_id, "assistant", err_text, payload={"kind": "error", "detail": str(exc)})
            yield {"event": "error", "data": json.dumps({"message": err_text, "detail": str(exc)})}
            yield {"event": "done", "data": json.dumps({"message_id": msg["id"], "chat_id": chat_id})}
            return

        final_visible_delta = stream_filter.finish()
        if final_visible_delta:
            yield {"event": "text", "data": json.dumps({"delta": final_visible_delta})}
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
                "view_type": _get_view_type(chat_id),
                **_df_to_payload(df),
            }
            yield {"event": "result", "data": json.dumps(result_payload, default=str)}

        full_text = _finalize_visible_answer(full_text, question, result_payload)
        assistant_payload: dict[str, Any] = {"kind": "result" if result_payload else "text", "model": "agent"}
        if result_payload:
            assistant_payload["result"] = result_payload
        msg = DB.add_message(chat_id, "assistant", full_text, payload=assistant_payload)
        DB.add_query_loop_metrics(
            chat_id=chat_id,
            message_id=user_message_id,
            question=question,
            route="mcp_agent",
            **loop_metrics,
        )
        yield {"event": "done", "data": json.dumps({"message_id": msg["id"], "chat_id": chat_id})}
    finally:
        span.end()


async def _run_local_agent(
    chat_id: str,
    question: str,
    source: DataSource,
    history: list[dict[str, Any]],
    request_id: str,
    model_used: str,
    llm_router: LLMRouter | None = None,
    user_message_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    span = TRACER.start_span("local_agent")
    span.set_attribute("question", question)
    span.set_attribute("source_name", source.display_name)
    try:
        """Drive a function-calling loop against the local DuckDB source.

        Used when the intent classifier picks intent_type="multi_step" — the question
        chains two queries where the second depends on the first's result. The LLM
        calls run_sql once to find the anchor (e.g. peak month), reads the result,
        then calls run_sql again parameterized by that anchor."""
        router = llm_router or ROUTER
        agent = _get_domain_agent(chat_id)
        domain_prompt = agent.get_system_prompt() if agent else ""
        domain_tools = agent.get_tools() if agent else []

        base_prompt = build_local_agent_system_prompt(source.display_name, source.schema)
        system_prompt = f"{domain_prompt}\n\n{base_prompt}" if domain_prompt else base_prompt

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
        }] + domain_tools

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
        stream_filter = _DSMLStreamFilter()
        loop_metrics = {"round_count": 0, "tool_call_count": 0, "tool_error_count": 0, "thinking_event_count": 0}

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
                    loop_metrics["tool_call_count"] += 1
                    loop_metrics["thinking_event_count"] += 1
                    loop_metrics["round_count"] = max(loop_metrics["round_count"], int(ev.get("round") or 0) + 1)
                    sql_arg = (ev.get("args") or {}).get("query", "")
                    preview = sql_arg.replace("\n", " ").strip()[:120]
                    step = f"Querying: {preview}{'…' if len(sql_arg) > 120 else ''}"
                    yield {"event": "thinking", "data": json.dumps({"step": step})}
                elif kind == "tool_result":
                    loop_metrics["thinking_event_count"] += 1
                    if ev.get("error"):
                        loop_metrics["tool_error_count"] += 1
                        yield {"event": "thinking", "data": json.dumps({"step": "Query returned an error — adjusting"})}
                    else:
                        yield {"event": "thinking", "data": json.dumps({"step": "Got data"})}
                elif kind == "text":
                    delta = ev.get("delta") or ""
                    full_text_parts.append(delta)
                    visible_delta = stream_filter.feed(delta)
                    if visible_delta:
                        yield {"event": "text", "data": json.dumps({"delta": visible_delta})}
        except LLMUnavailable as exc:
            err_msg = "All language models are rate-limited right now. Wait a minute and retry."
            DB.add_message(chat_id, "assistant", err_msg, payload={"kind": "error", "detail": str(exc)})
            yield {"event": "error", "data": json.dumps({"message": err_msg, "detail": str(exc)})}
            yield {"event": "done", "data": json.dumps({"chat_id": chat_id})}
            return

        final_visible_delta = stream_filter.finish()
        if final_visible_delta:
            yield {"event": "text", "data": json.dumps({"delta": final_visible_delta})}
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
                "view_type": _get_view_type(chat_id),
                **_df_to_payload(df),
            }
            yield {"event": "result", "data": json.dumps(result_payload, default=str)}

        full_text = _finalize_visible_answer(full_text, question, result_payload)
        payload: dict[str, Any] = {"kind": "result" if result_payload else "text", "model": model_used}
        if result_payload:
            payload["result"] = result_payload
        msg = DB.add_message(chat_id, "assistant", full_text, payload=payload)
        DB.add_query_loop_metrics(
            chat_id=chat_id,
            message_id=user_message_id,
            question=question,
            route="local_agent",
            **loop_metrics,
        )
        yield {"event": "done", "data": json.dumps({"message_id": msg["id"], "chat_id": chat_id})}
    finally:
        span.end()


async def _run_multi_source_agent(
    chat_id: str,
    question: str,
    selected: list[tuple[dict[str, Any], DataSource]],
    history: list[dict[str, Any]],
    request_id: str,
    allowed_connector_ids: set[str] | None = None,
    llm_router: LLMRouter | None = None,
    user_message_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    span = TRACER.start_span("multi_source_agent")
    span.set_attribute("question", question)
    try:
        router = llm_router or ROUTER
        pool = get_pool()
        specs, routing = pool.aggregate_tools(allowed_connector_ids=allowed_connector_ids)
        loop = asyncio.get_running_loop()
        source_summaries = await loop.run_in_executor(None, lambda: _prepare_workspace_sync(chat_id, selected))
        join_candidates = _detect_join_candidates(source_summaries)
        span.set_attribute("source_count", len(source_summaries))

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

        agent = _get_domain_agent(chat_id)
        domain_tools = agent.get_tools() if agent else []

        tool_specs = [{
            "name": "run_sql",
            "description": "Execute a read-only DuckDB SELECT against the per-chat workspace tables. Use this for joins, aggregation, filtering, and final result shaping.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "DuckDB SELECT query against workspace tables."}},
                "required": ["query"],
                "additionalProperties": False,
            },
        }] + specs + domain_tools

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
        stream_filter = _DSMLStreamFilter()
        loop_metrics = {"round_count": 0, "tool_call_count": 0, "tool_error_count": 0, "thinking_event_count": 0}
        try:
            async for ev in router.agent_loop_stream(
                request_id=request_id,
                user_question=question,
                conversation_summary=conversation_summary(history),
                tool_specs=tool_specs,
                connector_summary=connector_summary,
                on_tool_call=on_tool_call,
                system_prompt=_workspace_prompt(source_summaries, connector_summary, join_candidates, domain_prompt=_get_domain_prompt(chat_id)),
            ):
                kind = ev["kind"]
                if kind == "tool_call":
                    loop_metrics["tool_call_count"] += 1
                    loop_metrics["thinking_event_count"] += 1
                    loop_metrics["round_count"] = max(loop_metrics["round_count"], int(ev.get("round") or 0) + 1)
                    if ev["name"] == "run_sql":
                        sql_arg = (ev.get("args") or {}).get("query", "")
                        preview = sql_arg.replace("\n", " ").strip()[:120]
                        yield {"event": "thinking", "data": json.dumps({"step": f"Querying workspace: {preview}{'…' if len(sql_arg) > 120 else ''}"})}
                    else:
                        connector_id = routing.get(ev["name"])
                        cname = name_lookup.get(connector_id, "connected source")
                        yield {"event": "thinking", "data": json.dumps({"step": f"Fetching data from {cname}"})}
                elif kind == "tool_result":
                    loop_metrics["thinking_event_count"] += 1
                    if ev.get("error"):
                        loop_metrics["tool_error_count"] += 1
                        yield {"event": "thinking", "data": json.dumps({"step": f"{ev['name']} returned an error — adjusting"})}
                    else:
                        yield {"event": "thinking", "data": json.dumps({"step": f"{ev['name']} returned data"})}
                elif kind == "text":
                    delta = ev.get("delta") or ""
                    full_text_parts.append(delta)
                    visible_delta = stream_filter.feed(delta)
                    if visible_delta:
                        yield {"event": "text", "data": json.dumps({"delta": visible_delta})}
        except LLMUnavailable as exc:
            err_msg = "The language model is unavailable, so I can't run a multi-source agent query right now."
            msg = DB.add_message(chat_id, "assistant", err_msg, payload={"kind": "error", "detail": str(exc)})
            yield {"event": "error", "data": json.dumps({"message": err_msg, "detail": str(exc)})}
            yield {"event": "done", "data": json.dumps({"message_id": msg["id"], "chat_id": chat_id})}
            return
        finally:
            span.end()

        final_visible_delta = stream_filter.finish()
        if final_visible_delta:
            yield {"event": "text", "data": json.dumps({"delta": final_visible_delta})}
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
                "view_type": _get_view_type(chat_id),
                **_df_to_payload(df),
            }
            yield {"event": "result", "data": json.dumps(result_payload, default=str)}
        elif source_summaries:
            full_text = full_text if full_text != "(no answer)" else "I fetched data, but did not get a final table to show."

        full_text = _finalize_visible_answer(full_text, question, result_payload)
        payload: dict[str, Any] = {"kind": "result" if result_payload else "text", "model": "multi-source-agent"}
        if result_payload:
            payload["result"] = result_payload
        msg = DB.add_message(chat_id, "assistant", full_text, payload=payload)
        DB.add_query_loop_metrics(
            chat_id=chat_id,
            message_id=user_message_id,
            question=question,
            route="multi_source_agent",
            **loop_metrics,
        )
        yield {"event": "done", "data": json.dumps({"message_id": msg["id"], "chat_id": chat_id})}
    finally:
        span.end()


def _load_history(chat_id: str | None, owner_id: str = "legacy", include_legacy: bool = False) -> list[dict[str, Any]]:
    if not chat_id:
        return []
    chat = DB.get_chat(chat_id, owner_id=owner_id, include_legacy=include_legacy)
    if not chat:
        return []
    return [{"role": m["role"], "content": m["content"]} for m in chat["messages"]]


async def _load_query_sources(
    source_ids: list[str],
    active_row: dict[str, Any] | None,
    *,
    use_active_fallback: bool,
    owner_id: str = "legacy",
) -> list[tuple[dict[str, Any], DataSource]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source_id in source_ids:
        if source_id == "mcp" or source_id in seen:
            continue
        row = DB.get_source(source_id, owner_id=owner_id)
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
async def query_endpoint(body: QueryRequest, request: Request, background_tasks: BackgroundTasks):
    with TRACER.start_as_current_span("query") as span:
        trace_id = format(span.get_span_context().trace_id, '032x')
        owner_id = _current_user_id(request)
        include_legacy = _is_test_user(request)
        if body.chat_id and not DB.get_chat(body.chat_id, owner_id=owner_id, include_legacy=include_legacy):
            raise HTTPException(status_code=404, detail="Chat not found")
        chat_id = body.chat_id or DB.create_chat(owner_id=owner_id)["id"]
        llm_router = _router_for_model_mode(body.model_mode)
        model_preset = _model_preset_for_mode(body.model_mode)
        if body.project_id:
            if not DB.get_project(body.project_id, owner_id=owner_id):
                raise HTTPException(status_code=404, detail="Project not found")
            DB.update_chat_project(chat_id, body.project_id, owner_id=owner_id)
        chat = DB.get_chat(chat_id, owner_id=owner_id, include_legacy=include_legacy)
        if chat and chat.get("project_id"):
            await ensure_project_context(chat["project_id"])

        question = body.question.strip()
        if not question:
            raise HTTPException(status_code=400, detail="Question is required")
        if body.project_id:
            _learn_project_vocabulary(body.project_id, owner_id, question)

        active_row = DB.get_active_source(owner_id=owner_id)
        pool = get_pool()
        allowed_mcp_ids = _allowed_mcp_connector_ids_for_project(chat.get("project_id") if chat else None)
        has_mcp = any(s.status == "connected" and s.id in allowed_mcp_ids for s in pool.connectors.values())
        requested_source_ids = body.source_ids or []
        selected_mcp = "mcp" in requested_source_ids
        selected_sources = await _load_query_sources(
            requested_source_ids,
            active_row,
            use_active_fallback=not body.source_ids,
            owner_id=owner_id,
        )

        if not selected_sources and not has_mcp:
            raise HTTPException(status_code=400, detail="Attach a source first")

        active_for_legacy = selected_sources[0] if len(selected_sources) == 1 else None
        active_row = active_for_legacy[0] if active_for_legacy else active_row
        source: DataSource | None = active_for_legacy[1] if active_for_legacy else None

        # Store source_ids in user message payload so we can restore them when loading chat history
        user_payload: dict[str, Any] = {"source_ids": [row["id"] for row, _ in selected_sources]}
        user_msg = DB.add_message(chat_id, "user", question, payload=user_payload, trace_id=trace_id)
        chat = DB.get_chat(chat_id, owner_id=owner_id, include_legacy=include_legacy)
        if chat and (not chat.get("title") or chat["title"] == "New chat"):
            DB.update_chat_title(chat_id, question[:60], owner_id=owner_id)

        history = _load_history(chat_id, owner_id=owner_id, include_legacy=include_legacy)
        project_instructions: dict[str, Any] | None = None
        source_instructions: dict[str, Any] | None = None
        memory_snippets: list[dict[str, Any]] = []
        if chat and chat.get("project_id"):
            project_instructions = DB.get_project_instructions(chat["project_id"])
            if project_instructions is None:
                project = DB.get_project(chat["project_id"], owner_id=owner_id)
                source_rows = [DB.get_source(f.get("source_id"), owner_id=owner_id) for f in (project or {}).get("files", []) if f.get("source_id")]
                project_instructions = {
                    "category": detect_project_category(project or {}, [r for r in source_rows if r]),
                    "notes": "",
                    "metrics": {},
                    "entities": {},
                }
                DB.upsert_project_instructions(chat["project_id"], project_instructions)
            DB.rebuild_project_memory(chat["project_id"])
            memory_snippets = DB.search_project_memory(chat["project_id"], question, limit=5)
            notes = DB.list_project_notes(chat["project_id"])[:6]
            if notes:
                note_lines = "\n".join(f"- {n['title']}: {n['content'][:300]}" for n in notes)
                history.append({"role": "project_notes", "content": f"Saved project notes:\n{note_lines}"})
        if active_row:
            source_instructions = _get_or_create_source_instructions(active_row["id"])
        request_id = uuid.uuid4().hex[:12]

        # Explicitly capture current context for the background stream
        from opentelemetry.context import attach, detach
        from opentelemetry.trace import set_span_in_context
        parent_context = set_span_in_context(span)

        async def event_stream() -> AsyncIterator[dict[str, Any]]:
            # Re-attach parent context inside the generator thread/loop
            token = attach(parent_context)
            try:
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

                # ── Travel domain fast-path ─────────────────────────────────────────
                _proj_category = (project_instructions or {}).get("category", "")
                _travel_keywords = ("flight", "airline", "airport", "fly ", "depart",
                                    "cabin class", "economy class", "business class",
                                    "travel to", "itinerary", " pnr ")
                _is_travel_query = (
                    _proj_category == "travel"
                    or any(kw in question.lower() for kw in _travel_keywords)
                )
                if _is_travel_query and CONFIG.duffel_api_token:
                    try:
                        orchestrator = TravelOrchestrator()
                        _src_ids = [row["id"] for row, _ in selected_sources]
                        async for ev in orchestrator.run(
                            question=question,
                            chat_id=chat_id,
                            source_ids=_src_ids or None,
                            request_id=request_id,
                            router=llm_router,
                            pool=pool,
                            db=DB,
                            config=CONFIG,
                        ):
                            if ev.get("kind") == "thinking":
                                yield {"event": "thinking", "data": json.dumps({"step": ev.get("step", ""), "progress": ev.get("progress")})}
                            elif ev.get("kind") == "travel_result":
                                _travel_payload = {
                                    "kind": "travel_result",
                                    "text": ev.get("text", ""),
                                    "travel_offers": ev.get("travel_offers", []),
                                    "travel_intent": ev.get("travel_intent", {}),
                                }
                                DB.add_message(chat_id, "assistant", ev.get("text", ""), payload=_travel_payload)
                                yield {"event": "travel_result", "data": json.dumps(_travel_payload)}
                                yield {"event": "done", "data": json.dumps({"chat_id": chat_id})}
                        return
                    except Exception as exc:
                        log_event(LOGGERS["errors"], "travel_orchestrator_error", request_id=request_id, error=str(exc))
                        # Fall through to standard SQL path on error
                # ── End travel domain fast-path ────────────────────────────────────

                if len(selected_sources) > 1 or selected_mcp or (source is None and has_mcp):

                    try:
                        async for ev in _run_multi_source_agent(chat_id, question, selected_sources, history, request_id, allowed_mcp_ids, llm_router, user_msg["id"]):
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
                        intent, model_used, usage = await loop.run_in_executor(
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
                        if usage:
	                            DB.add_token_usage(
	                                project_id=chat.get("project_id") if chat else None,
	                                user_id=owner_id,
	                                model=model_used,
	                                prompt_tokens=usage.get("prompt_tokens", 0),
	                                completion_tokens=usage.get("completion_tokens", 0),
	                                purpose="chat",
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
                        async for ev in _run_multi_source_agent(chat_id, question, selected_sources, history, request_id, allowed_mcp_ids, llm_router, user_msg["id"]):
                            yield ev
                        return

                    # Compound question that needs sequential SQL — route to local agent loop.
                    if intent.get("intent_type") == "multi_step" and source is not None:
                        async for ev in _run_local_agent(chat_id, question, source, history, request_id, model_used, llm_router, user_msg["id"]):
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
                            async for ev in _run_mcp_agent(chat_id, question, history, request_id, allowed_mcp_ids, llm_router, user_msg["id"]):
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
                        "view_type": _get_view_type(chat_id),
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
                    stream_filter = _DSMLStreamFilter()

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
                                visible_chunk = stream_filter.feed(chunk)
                                if visible_chunk:
                                    yield {"event": "text", "data": json.dumps({"delta": visible_chunk})}
                        except LLMUnavailable as exc:
                            text = deterministic_summary(question, df, len(df))
                            full_text_parts = [text]
                            yield {"event": "text", "data": json.dumps({"delta": text})}
                    else:
                        text = deterministic_summary(question, df, len(df))
                        full_text_parts = [text]
                        yield {"event": "text", "data": json.dumps({"delta": text})}

                    final_visible_delta = stream_filter.finish()
                    if final_visible_delta and llm_router.available:
                        yield {"event": "text", "data": json.dumps({"delta": final_visible_delta})}
                    full_text = _finalize_visible_answer("".join(full_text_parts) or "(no answer)", question, result_payload)
                    
                    # Log tokens for the answer (estimated for stream)
                    if llm_router.available:
                        prompt_for_answer = build_answer_prompt(
                            user_question=question,
                            intent=intent,
                            result_sample=sample,
                            row_count=len(df),
                            char_budget=llm_router.char_budget,
                            sql=plan.sql,
                            total_row=total_row,
                        )
                        DB.add_token_usage(
                            project_id=chat.get("project_id") if chat else None,
                            user_id=owner_id,
	                            model=model_used,
	                            prompt_tokens=estimate_tokens(prompt_for_answer),
	                            completion_tokens=estimate_tokens(full_text),
	                            purpose="chat",
	                        )

                    assistant_payload = {
                        "kind": "result",
                        "model": model_used,
                        "result": result_payload,
                    }
                    msg = DB.add_message(chat_id, "assistant", full_text, payload=assistant_payload)

                    # Hallucination evaluation
                    if sample and llm_router.available:
                        context_str = json.dumps(sample, indent=2)
                        background_tasks.add_task(
                            evaluate_hallucination_background,
                            chat_id,
                            msg["id"],
                            question,
                            full_text,
                            context_str,
                            parent_context
                        )

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
            finally:
                detach(token)

        return EventSourceResponse(event_stream())
