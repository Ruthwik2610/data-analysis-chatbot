from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS user_sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_jti TEXT NOT NULL UNIQUE,
  ip_address TEXT,
  user_agent TEXT,
  expires_at REAL NOT NULL,
  revoked_at REAL,
  created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_jti ON user_sessions(token_jti);

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL DEFAULT 'legacy',
  title TEXT NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS project_files (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  file_path TEXT,
  source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
  sheet_name TEXT,
  created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_project_files_project ON project_files(project_id);

CREATE TABLE IF NOT EXISTS project_notes (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  source_message_id TEXT,
  created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_project_notes_project ON project_notes(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS chats (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL DEFAULT 'legacy',
  title TEXT,
  project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
  created_at REAL,
  updated_at REAL
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  payload TEXT,
  trace_id TEXT,
  created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, created_at);

CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL DEFAULT 'legacy',
  name TEXT,
  kind TEXT,
  rows INTEGER,
  schema_json TEXT,
  origin TEXT,
  active INTEGER DEFAULT 0,
  created_at REAL
);

CREATE TABLE IF NOT EXISTS connectors (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL DEFAULT 'legacy',
  kind TEXT,
  label TEXT,
  config TEXT,
  created_at REAL
);

CREATE TABLE IF NOT EXISTS source_instructions (
  source_id TEXT PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
  instructions_json TEXT NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS project_instructions (
  project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
  instructions_json TEXT NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS mcp_connectors (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL DEFAULT 'legacy',
  name TEXT NOT NULL,
  description TEXT,
  generated_description TEXT,
  description_status TEXT NOT NULL DEFAULT 'metadata',
  scope TEXT NOT NULL DEFAULT 'global',
  transport TEXT NOT NULL DEFAULT 'http',
  url TEXT,
  command TEXT,
  args_json TEXT,
  tools_json TEXT,
  status TEXT NOT NULL DEFAULT 'connecting',
  last_error TEXT,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS project_mcp_connectors (
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  connector_id TEXT NOT NULL REFERENCES mcp_connectors(id) ON DELETE CASCADE,
  created_at REAL NOT NULL,
  PRIMARY KEY (project_id, connector_id)
);

CREATE INDEX IF NOT EXISTS idx_project_mcp_project ON project_mcp_connectors(project_id);

CREATE TABLE IF NOT EXISTS workbook_mcp_metadata (
  connector_id TEXT PRIMARY KEY REFERENCES mcp_connectors(id) ON DELETE CASCADE,
  db_path TEXT NOT NULL,
  table_names_json TEXT NOT NULL,
  display_name TEXT NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS workbook_mcp_deployments (
  connector_id TEXT PRIMARY KEY REFERENCES mcp_connectors(id) ON DELETE CASCADE,
  worker_name TEXT NOT NULL,
  worker_url TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS workbook_views (
  id TEXT PRIMARY KEY,
  connector_id TEXT NOT NULL REFERENCES mcp_connectors(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  sql TEXT NOT NULL,
  columns_json TEXT NOT NULL DEFAULT '[]',
  row_count INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  UNIQUE(connector_id, name)
);

CREATE INDEX IF NOT EXISTS idx_workbook_views_connector ON workbook_views(connector_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS test_suites (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS test_queries (
  id TEXT PRIMARY KEY,
  suite_id TEXT NOT NULL REFERENCES test_suites(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'Uncategorized',
  expected_answer TEXT,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS test_runs (
  id TEXT PRIMARY KEY,
  suite_id TEXT NOT NULL REFERENCES test_suites(id) ON DELETE CASCADE,
  snapshot_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'running',
  total_count INTEGER NOT NULL DEFAULT 0,
  completed_count INTEGER NOT NULL DEFAULT 0,
  completed_at REAL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS test_evaluations (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
  query_id TEXT NOT NULL REFERENCES test_queries(id) ON DELETE CASCADE,
  answer TEXT,
  latency_ms REAL,
  grade TEXT, -- 'Pass', 'Fail', 'Partial', 'Error'
  reason TEXT,
  ai_grade TEXT, -- AI-generated grade
  ai_reason TEXT, -- AI-generated reasoning
  trace_id TEXT,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS user_feedback (
  id TEXT PRIMARY KEY,
  chat_id TEXT REFERENCES chats(id) ON DELETE CASCADE,
  message_id TEXT REFERENCES messages(id) ON DELETE CASCADE,
  rating INTEGER, -- e.g. 1-5 or simple boolean
  category TEXT NOT NULL DEFAULT 'feedback',
  status TEXT NOT NULL DEFAULT 'open',
  comment TEXT,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS token_usage (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
  model TEXT NOT NULL,
  purpose TEXT NOT NULL DEFAULT 'chat',
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS hallucination_logs (
  id TEXT PRIMARY KEY,
  chat_id TEXT REFERENCES chats(id) ON DELETE CASCADE,
  message_id TEXT REFERENCES messages(id) ON DELETE CASCADE,
  score REAL NOT NULL, -- 1.0 = faithful, < 1.0 = hallucination
  reason TEXT,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS query_loop_metrics (
  id TEXT PRIMARY KEY,
  chat_id TEXT REFERENCES chats(id) ON DELETE CASCADE,
  message_id TEXT REFERENCES messages(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  route TEXT NOT NULL,
  round_count INTEGER NOT NULL DEFAULT 0,
  tool_call_count INTEGER NOT NULL DEFAULT 0,
  tool_error_count INTEGER NOT NULL DEFAULT 0,
  thinking_event_count INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_query_loop_metrics_created ON query_loop_metrics(created_at DESC);

CREATE TABLE IF NOT EXISTS travel_journeys (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL DEFAULT 'legacy',
  chat_id TEXT REFERENCES chats(id) ON DELETE SET NULL,
  origin TEXT,
  destination TEXT,
  departure_date TEXT,
  return_date TEXT,
  passengers INTEGER,
  cabin_class TEXT,
  traveler_tier TEXT,
  budget_limit_usd REAL,
  selected_offer_id TEXT,
  flight_offer_json TEXT,
  status TEXT NOT NULL DEFAULT 'saved',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_travel_journeys_owner ON travel_journeys(owner_id, created_at DESC);
"""


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            con.executescript(SCHEMA)
            self._ensure_column(con, "projects", "owner_id", "TEXT NOT NULL DEFAULT 'legacy'")
            self._ensure_column(con, "chats", "owner_id", "TEXT NOT NULL DEFAULT 'legacy'")
            self._ensure_column(con, "chats", "project_id", "TEXT REFERENCES projects(id) ON DELETE SET NULL")
            self._ensure_column(con, "sources", "owner_id", "TEXT NOT NULL DEFAULT 'legacy'")
            self._ensure_column(con, "connectors", "owner_id", "TEXT NOT NULL DEFAULT 'legacy'")
            self._ensure_column(con, "mcp_connectors", "owner_id", "TEXT NOT NULL DEFAULT 'legacy'")
            self._ensure_column(con, "project_files", "source_id", "TEXT REFERENCES sources(id) ON DELETE SET NULL")
            self._ensure_column(con, "messages", "trace_id", "TEXT")
            self._ensure_column(con, "test_suites", "metadata_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(con, "test_queries", "expected_answer", "TEXT")
            self._ensure_column(con, "test_runs", "status", "TEXT NOT NULL DEFAULT 'running'")
            self._ensure_column(con, "test_runs", "total_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(con, "test_runs", "completed_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(con, "test_runs", "completed_at", "REAL")
            self._ensure_column(con, "test_evaluations", "trace_id", "TEXT")
            self._ensure_column(con, "test_evaluations", "ai_grade", "TEXT")
            self._ensure_column(con, "test_evaluations", "ai_reason", "TEXT")
            self._ensure_column(con, "user_feedback", "category", "TEXT NOT NULL DEFAULT 'feedback'")
            self._ensure_column(con, "user_feedback", "status", "TEXT NOT NULL DEFAULT 'open'")
            self._ensure_column(con, "token_usage", "purpose", "TEXT NOT NULL DEFAULT 'chat'")
            self._ensure_column(con, "travel_journeys", "owner_id", "TEXT NOT NULL DEFAULT 'legacy'")
            self._ensure_project_memory_table(con)
            con.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.db_path, timeout=10)
        con.execute("PRAGMA foreign_keys = ON")
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def _ensure_project_memory_table(self, con: sqlite3.Connection) -> None:
        try:
            con.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS project_memory_fts
                USING fts5(project_id UNINDEXED, kind UNINDEXED, ref_id UNINDEXED, title, content)
                """
            )
        except sqlite3.OperationalError:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS project_memory_fts (
                  project_id TEXT,
                  kind TEXT,
                  ref_id TEXT,
                  title TEXT,
                  content TEXT
                )
                """
            )

    def _ensure_column(self, con: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    # -- users ---------------------------------------------------------------
    def create_user(self, email: str, password_hash: str) -> dict[str, Any]:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._conn() as con:
            con.execute(
                "INSERT INTO users (id, email, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, email, password_hash, now, now),
            )
        return {"id": user_id, "email": email, "created_at": now, "updated_at": now}

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def update_user_password(self, user_id: str, password_hash: str) -> None:
        with self._conn() as con:
            con.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (password_hash, time.time(), user_id),
            )

    def create_session(self, user_id: str, jti: str, ip: str | None, ua: str | None, expires_at: float) -> dict[str, Any]:
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO user_sessions (id, user_id, token_jti, ip_address, user_agent, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, user_id, jti, ip, ua, expires_at, now),
            )
        return {"id": session_id, "user_id": user_id, "token_jti": jti, "expires_at": expires_at}

    def get_active_session(self, jti: str) -> dict[str, Any] | None:
        now = time.time()
        with self._conn() as con:
            row = con.execute(
                "SELECT * FROM user_sessions WHERE token_jti = ? AND expires_at > ? AND revoked_at IS NULL",
                (jti, now),
            ).fetchone()
        return dict(row) if row else None

    def revoke_session(self, jti: str) -> None:
        with self._conn() as con:
            con.execute("UPDATE user_sessions SET revoked_at = ? WHERE token_jti = ?", (time.time(), jti))

    # -- travel journeys -----------------------------------------------------
    def create_travel_journey(self, owner_id: str, chat_id: str | None, intent: dict[str, Any], offer: dict[str, Any]) -> dict[str, Any]:
        journey_id = f"journey_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO travel_journeys (
                  id, owner_id, chat_id, origin, destination, departure_date, return_date,
                  passengers, cabin_class, traveler_tier, budget_limit_usd, selected_offer_id,
                  flight_offer_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    journey_id, owner_id, chat_id,
                    intent.get("origin"), intent.get("destination"),
                    intent.get("departure_date"), intent.get("return_date"),
                    intent.get("passengers"), intent.get("cabin_class"),
                    intent.get("traveler_tier"), intent.get("budget_limit_usd"),
                    offer.get("offer_id"), json.dumps(offer), "saved",
                    now, now
                )
            )
        return {"id": journey_id, "created_at": now}

    def list_travel_journeys(self, owner_id: str = "legacy") -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute("SELECT * FROM travel_journeys WHERE owner_id = ? ORDER BY created_at DESC", (owner_id,)).fetchall()
        return [dict(r) for r in rows]

    # -- chats ---------------------------------------------------------------
    def create_chat(self, title: str | None = None, project_id: str | None = None, owner_id: str = "legacy") -> dict[str, Any]:
        chat_id = f"chat_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._conn() as con:
            con.execute(
                "INSERT INTO chats (id, owner_id, title, project_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, owner_id, title, project_id, now, now),
            )
        return {"id": chat_id}

    def list_chats(
        self,
        project_id: str | None = None,
        owner_id: str = "legacy",
        include_legacy: bool = False,
    ) -> list[dict[str, Any]]:
        with self._conn() as con:
            owners = [owner_id]
            if include_legacy and owner_id != "legacy":
                owners.append("legacy")
            
            placeholders = ",".join(["?"] * len(owners))
            
            if project_id and project_id != "none":
                rows = con.execute(
                    f"SELECT * FROM chats WHERE owner_id IN ({placeholders}) AND project_id = ? ORDER BY updated_at DESC",
                    (*owners, project_id),
                ).fetchall()
            else:
                rows = con.execute(
                    f"SELECT * FROM chats WHERE owner_id IN ({placeholders}) AND project_id IS NULL ORDER BY updated_at DESC",
                    owners,
                ).fetchall()
        return [dict(r) for r in rows]

    def get_chat(
        self,
        chat_id: str,
        owner_id: str | None = None,
        include_legacy: bool = False,
    ) -> dict[str, Any] | None:
        with self._conn() as con:
            if owner_id is None:
                row = con.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
            else:
                owners = [owner_id]
                if include_legacy and owner_id != "legacy":
                    owners.append("legacy")
                placeholders = ",".join(["?"] * len(owners))
                row = con.execute(f"SELECT * FROM chats WHERE id = ? AND owner_id IN ({placeholders})", (chat_id, *owners)).fetchone()
            if not row:
                return None
            msg_rows = con.execute(
                "SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC",
                (chat_id,),
            ).fetchall()
            
            # Fetch source metadata used in this chat
            # We look for result payloads that contain source info
            source_ids = set()
            for m in msg_rows:
                if m["payload"]:
                    try:
                        p = json.loads(m["payload"])
                        if p.get("source", {}).get("id"):
                            source_ids.add(p["source"]["id"])
                    except: pass
            
            sources = []
            if source_ids:
                placeholders = ",".join(["?"] * len(source_ids))
                s_rows = con.execute(f"SELECT id, name, kind FROM sources WHERE id IN ({placeholders})", list(source_ids)).fetchall()
                sources = [dict(s) for s in s_rows]

        return {
            **dict(row),
            "messages": [
                {**dict(m), "payload": json.loads(m["payload"]) if m["payload"] else None}
                for m in msg_rows
            ],
            "sources": sources,
            "source_ids": list(source_ids),
        }

    def update_chat_title(self, chat_id: str, title: str, owner_id: str | None = None) -> None:
        with self._conn() as con:
            owner_clause = " AND owner_id = ?" if owner_id is not None else ""
            params: tuple[Any, ...] = (title, time.time(), chat_id, owner_id) if owner_id is not None else (title, time.time(), chat_id)
            con.execute(
                f"UPDATE chats SET title = ?, updated_at = ? WHERE id = ?{owner_clause}",
                params,
            )

    def touch_chat(self, chat_id: str) -> None:
        with self._conn() as con:
            con.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (time.time(), chat_id))

    def delete_chat(self, chat_id: str, owner_id: str | None = None) -> None:
        with self._conn() as con:
            if owner_id is None:
                con.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            else:
                con.execute("DELETE FROM chats WHERE id = ? AND owner_id = ?", (chat_id, owner_id))

    def add_message(self, chat_id: str, role: str, content: str, payload: dict | None = None, trace_id: str | None = None) -> dict[str, Any]:
        # Automatically detect trace_id from current OpenTelemetry context if not provided
        if not trace_id:
            try:
                from opentelemetry import trace
                span = trace.get_current_span()
                if span and span.get_span_context().is_valid:
                    trace_id = format(span.get_span_context().trace_id, '032x')
            except ImportError:
                pass

        msg_id = f"msg_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._conn() as con:
            con.execute(
                "INSERT INTO messages (id, chat_id, role, content, payload, trace_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (msg_id, chat_id, role, content, json.dumps(payload) if payload else None, trace_id, now),
            )
            con.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
        return {"id": msg_id, "role": role, "content": content, "payload": payload, "trace_id": trace_id, "created_at": now}

    # -- sources -------------------------------------------------------------
    def upsert_source(
        self,
        *,
        source_id: str,
        name: str,
        kind: str,
        rows: int,
        schema_json: str,
        origin: dict[str, Any] | None,
        owner_id: str = "legacy",
    ) -> None:
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO sources (id, owner_id, name, kind, rows, schema_json, origin, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(id) DO UPDATE SET
                  owner_id=excluded.owner_id,
                  name=excluded.name, kind=excluded.kind, rows=excluded.rows,
                  schema_json=excluded.schema_json, origin=excluded.origin
                """,
                (
                    source_id,
                    owner_id,
                    name,
                    kind,
                    rows,
                    schema_json,
                    json.dumps(origin) if origin else None,
                    time.time(),
                ),
            )

    def list_sources(self, owner_id: str = "legacy") -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT id, name, kind, rows, active, created_at FROM sources WHERE owner_id = ? ORDER BY created_at DESC",
                (owner_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_source(self, source_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
        with self._conn() as con:
            if owner_id is None:
                row = con.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
            else:
                row = con.execute("SELECT * FROM sources WHERE id = ? AND owner_id = ?", (source_id, owner_id)).fetchone()
        return dict(row) if row else None

    def source_name_exists(self, name: str, owner_id: str = "legacy") -> bool:
        with self._conn() as con:
            row = con.execute(
                "SELECT 1 FROM sources WHERE owner_id = ? AND LOWER(name) = LOWER(?) LIMIT 1",
                (owner_id, name),
            ).fetchone()
        return row is not None

    def get_source_instructions(self, source_id: str) -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute("SELECT instructions_json FROM source_instructions WHERE source_id = ?", (source_id,)).fetchone()
        if not row:
            return None
        return json.loads(row["instructions_json"])

    def upsert_source_instructions(self, source_id: str, instructions: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO source_instructions (source_id, instructions_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                  instructions_json=excluded.instructions_json,
                  updated_at=excluded.updated_at
                """,
                (source_id, json.dumps(instructions, default=str), now),
            )
        return {"source_id": source_id, "instructions": instructions, "updated_at": now}

    def delete_source(self, source_id: str, owner_id: str | None = None) -> None:
        with self._conn() as con:
            if owner_id is None:
                con.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            else:
                con.execute("DELETE FROM sources WHERE id = ? AND owner_id = ?", (source_id, owner_id))

    def set_active_source(self, source_id: str | None, owner_id: str = "legacy") -> None:
        with self._conn() as con:
            con.execute("UPDATE sources SET active = 0 WHERE owner_id = ?", (owner_id,))
            if source_id:
                con.execute("UPDATE sources SET active = 1 WHERE id = ? AND owner_id = ?", (source_id, owner_id))

    def get_active_source(self, owner_id: str = "legacy") -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute("SELECT * FROM sources WHERE owner_id = ? AND active = 1", (owner_id,)).fetchone()
        return dict(row) if row else None

    # -- connectors ----------------------------------------------------------
    def add_connector(self, *, kind: str, label: str, config: dict[str, Any], owner_id: str = "legacy") -> dict[str, Any]:
        conn_id = f"conn_{uuid.uuid4().hex[:10]}"
        with self._conn() as con:
            con.execute(
                "INSERT INTO connectors (id, owner_id, kind, label, config, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (conn_id, owner_id, kind, label, json.dumps(config), time.time()),
            )
        return {"id": conn_id, "owner_id": owner_id, "kind": kind, "label": label, "config": config}

    def list_connectors(self, owner_id: str = "legacy") -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute("SELECT * FROM connectors WHERE owner_id = ? ORDER BY created_at DESC", (owner_id,)).fetchall()
        return [{**dict(r), "config": json.loads(r["config"]) if r["config"] else {}} for r in rows]

    def delete_connector(self, connector_id: str, owner_id: str | None = None) -> None:
        with self._conn() as con:
            if owner_id is None:
                con.execute("DELETE FROM connectors WHERE id = ?", (connector_id,))
            else:
                con.execute("DELETE FROM connectors WHERE id = ? AND owner_id = ?", (connector_id, owner_id))

    def get_connector(self, connector_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
        with self._conn() as con:
            if owner_id is None:
                row = con.execute("SELECT * FROM connectors WHERE id = ?", (connector_id,)).fetchone()
            else:
                row = con.execute("SELECT * FROM connectors WHERE id = ? AND owner_id = ?", (connector_id, owner_id)).fetchone()
        if not row:
            return None
        return {**dict(row), "config": json.loads(row["config"]) if row["config"] else {}}

    # -- MCP connector metadata ---------------------------------------------
    @staticmethod
    def _redact_args(args: list[str] | None) -> list[str]:
        if not args:
            return []
        redacted: list[str] = []
        for arg in args:
            text = str(arg)
            if "://" in text and ("@" in text or ":" in text.split("://", 1)[-1]):
                redacted.append("[redacted]")
            else:
                redacted.append(text)
        return redacted

    @staticmethod
    def _mcp_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        raw_args = json.loads(data["args_json"]) if data.get("args_json") else []
        data["args"] = Storage._redact_args(raw_args)
        data["tools"] = json.loads(data["tools_json"]) if data.get("tools_json") else []
        data.pop("args_json", None)
        data.pop("tools_json", None)
        return data

    def upsert_mcp_connector(
        self,
        *,
        connector_id: str,
        name: str,
        scope: str,
        transport: str,
        url: str | None,
        command: str | None,
        args: list[str] | None,
        tools: list[dict[str, Any]] | None,
        status: str,
        last_error: str | None,
        description: str | None,
        generated_description: str | None,
        description_status: str,
        owner_id: str = "legacy",
    ) -> dict[str, Any]:
        now = time.time()
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO mcp_connectors (
                  id, owner_id, name, description, generated_description, description_status,
                  scope, transport, url, command, args_json, tools_json, status,
                  last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  owner_id=excluded.owner_id,
                  name=excluded.name,
                  description=excluded.description,
                  generated_description=excluded.generated_description,
                  description_status=excluded.description_status,
                  scope=excluded.scope,
                  transport=excluded.transport,
                  url=excluded.url,
                  command=excluded.command,
                  args_json=excluded.args_json,
                  tools_json=excluded.tools_json,
                  status=excluded.status,
                  last_error=excluded.last_error,
                  updated_at=excluded.updated_at
                """,
                (
                    connector_id,
                    owner_id,
                    name,
                    description,
                    generated_description,
                    description_status,
                    scope,
                    transport,
                    url,
                    command,
                    json.dumps(args or []),
                    json.dumps(tools or []),
                    status,
                    last_error,
                    now,
                    now,
                ),
            )
            row = con.execute("SELECT * FROM mcp_connectors WHERE id = ?", (connector_id,)).fetchone()
        return self._mcp_row_to_dict(row)

    def get_mcp_connector(self, connector_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
        with self._conn() as con:
            if owner_id is None:
                row = con.execute("SELECT * FROM mcp_connectors WHERE id = ?", (connector_id,)).fetchone()
            else:
                row = con.execute("SELECT * FROM mcp_connectors WHERE id = ? AND owner_id = ?", (connector_id, owner_id)).fetchone()
        return self._mcp_row_to_dict(row) if row else None

    def list_mcp_connectors(self, owner_id: str = "legacy") -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute("SELECT * FROM mcp_connectors WHERE owner_id = ? ORDER BY updated_at DESC", (owner_id,)).fetchall()
        return [self._mcp_row_to_dict(r) for r in rows]

    def update_mcp_generated_description(
        self,
        connector_id: str,
        generated_description: str | None,
        description_status: str,
    ) -> None:
        with self._conn() as con:
            con.execute(
                """
                UPDATE mcp_connectors
                SET generated_description = ?, description_status = ?, updated_at = ?
                WHERE id = ?
                """,
                (generated_description, description_status, time.time(), connector_id),
            )

    def bind_mcp_to_project(self, project_id: str, connector_id: str) -> None:
        with self._conn() as con:
            con.execute(
                """
                INSERT OR IGNORE INTO project_mcp_connectors (project_id, connector_id, created_at)
                VALUES (?, ?, ?)
                """,
                (project_id, connector_id, time.time()),
            )

    def unbind_mcp_from_project(self, project_id: str, connector_id: str) -> None:
        with self._conn() as con:
            con.execute(
                "DELETE FROM project_mcp_connectors WHERE project_id = ? AND connector_id = ?",
                (project_id, connector_id),
            )

    def list_project_mcp_connectors(self, project_id: str) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT mc.*
                FROM mcp_connectors mc
                JOIN project_mcp_connectors pmc ON pmc.connector_id = mc.id
                WHERE pmc.project_id = ?
                ORDER BY pmc.created_at ASC
                """,
                (project_id,),
            ).fetchall()
        return [self._mcp_row_to_dict(r) for r in rows]

    def connector_project_ids(self, connector_id: str) -> list[str]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT project_id FROM project_mcp_connectors WHERE connector_id = ? ORDER BY created_at ASC",
                (connector_id,),
            ).fetchall()
        return [r["project_id"] for r in rows]

    def allowed_mcp_connector_ids(self, project_id: str | None, owner_id: str = "legacy") -> set[str]:
        with self._conn() as con:
            rows = con.execute("SELECT id FROM mcp_connectors WHERE owner_id = ? AND scope = 'global'", (owner_id,)).fetchall()
            allowed = {r["id"] for r in rows}
            if project_id:
                project_rows = con.execute(
                    "SELECT connector_id FROM project_mcp_connectors WHERE project_id = ?",
                    (project_id,),
                ).fetchall()
                allowed.update(r["connector_id"] for r in project_rows)
        return allowed

    def upsert_workbook_mcp_metadata(
        self,
        *,
        connector_id: str,
        db_path: str,
        table_names: list[str],
        display_name: str,
    ) -> dict[str, Any]:
        now = time.time()
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO workbook_mcp_metadata (connector_id, db_path, table_names_json, display_name, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(connector_id) DO UPDATE SET
                  db_path=excluded.db_path,
                  table_names_json=excluded.table_names_json,
                  display_name=excluded.display_name,
                  updated_at=excluded.updated_at
                """,
                (connector_id, db_path, json.dumps(table_names), display_name, now),
            )
        return {
            "connector_id": connector_id,
            "db_path": db_path,
            "table_names": table_names,
            "display_name": display_name,
            "updated_at": now,
        }

    def get_workbook_mcp_metadata(self, connector_id: str) -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute(
                "SELECT * FROM workbook_mcp_metadata WHERE connector_id = ?",
                (connector_id,),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["table_names"] = json.loads(data.pop("table_names_json") or "[]")
        return data

    @staticmethod
    def _token_hash(public_token: str) -> str:
        return hashlib.sha256(public_token.encode("utf-8")).hexdigest()

    def upsert_workbook_mcp_deployment(
        self,
        *,
        connector_id: str,
        worker_name: str,
        worker_url: str,
        public_token: str,
    ) -> dict[str, Any]:
        now = time.time()
        existing = self.get_workbook_mcp_deployment(connector_id)
        created_at = existing["created_at"] if existing else now
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO workbook_mcp_deployments (connector_id, worker_name, worker_url, token_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(connector_id) DO UPDATE SET
                  worker_name=excluded.worker_name,
                  worker_url=excluded.worker_url,
                  token_hash=excluded.token_hash,
                  updated_at=excluded.updated_at
                """,
                (connector_id, worker_name, worker_url, self._token_hash(public_token), created_at, now),
            )
        return {
            "connector_id": connector_id,
            "worker_name": worker_name,
            "worker_url": worker_url,
            "created_at": created_at,
            "updated_at": now,
        }

    def get_workbook_mcp_deployment(self, connector_id: str) -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute(
                "SELECT connector_id, worker_name, worker_url, created_at, updated_at FROM workbook_mcp_deployments WHERE connector_id = ?",
                (connector_id,),
            ).fetchone()
        return dict(row) if row else None

    def verify_workbook_mcp_token(self, connector_id: str, public_token: str) -> bool:
        with self._conn() as con:
            row = con.execute(
                "SELECT token_hash FROM workbook_mcp_deployments WHERE connector_id = ?",
                (connector_id,),
            ).fetchone()
        if not row:
            return False
        return hmac.compare_digest(row["token_hash"], self._token_hash(public_token))

    def upsert_workbook_view(
        self,
        *,
        connector_id: str,
        name: str,
        sql: str,
        columns: list[str],
        row_count: int,
    ) -> dict[str, Any]:
        now = time.time()
        view_id = f"view_{uuid.uuid4().hex[:10]}"
        with self._conn() as con:
            existing = con.execute(
                "SELECT id, created_at FROM workbook_views WHERE connector_id = ? AND name = ?",
                (connector_id, name),
            ).fetchone()
            if existing:
                view_id = existing["id"]
                created_at = existing["created_at"]
            else:
                created_at = now
            con.execute(
                """
                INSERT INTO workbook_views (id, connector_id, name, sql, columns_json, row_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(connector_id, name) DO UPDATE SET
                  sql=excluded.sql,
                  columns_json=excluded.columns_json,
                  row_count=excluded.row_count,
                  updated_at=excluded.updated_at
                """,
                (view_id, connector_id, name, sql, json.dumps(columns), row_count, created_at, now),
            )
        return {
            "id": view_id,
            "connector_id": connector_id,
            "name": name,
            "sql": sql,
            "columns": columns,
            "row_count": row_count,
            "created_at": created_at,
            "updated_at": now,
        }

    def list_workbook_views(self, connector_id: str) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM workbook_views WHERE connector_id = ? ORDER BY name ASC",
                (connector_id,),
            ).fetchall()
        views = []
        for row in rows:
            item = dict(row)
            item["columns"] = json.loads(item.pop("columns_json") or "[]")
            views.append(item)
        return views

    def get_workbook_view(self, connector_id: str, name: str) -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute(
                "SELECT * FROM workbook_views WHERE connector_id = ? AND name = ?",
                (connector_id, name),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["columns"] = json.loads(item.pop("columns_json") or "[]")
        return item

    def delete_workbook_view(self, connector_id: str, name: str) -> None:
        with self._conn() as con:
            con.execute(
                "DELETE FROM workbook_views WHERE connector_id = ? AND name = ?",
                (connector_id, name),
            )

    # -- projects ------------------------------------------------------------
    def create_project(self, title: str, owner_id: str = "legacy") -> dict[str, Any]:
        clean_title = title.strip()
        if self.project_title_exists(clean_title, owner_id=owner_id):
            raise ValueError("A project with this name already exists")
        project_id = f"proj_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._conn() as con:
            con.execute(
                "INSERT INTO projects (id, owner_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (project_id, owner_id, clean_title, now, now),
            )
        return {"id": project_id, "owner_id": owner_id, "title": clean_title, "created_at": now, "updated_at": now}

    def project_title_exists(self, title: str, owner_id: str = "legacy", exclude_project_id: str | None = None) -> bool:
        sql = "SELECT 1 FROM projects WHERE owner_id = ? AND LOWER(title) = LOWER(?)"
        params: list[Any] = [owner_id, title.strip()]
        if exclude_project_id:
            sql += " AND id != ?"
            params.append(exclude_project_id)
        sql += " LIMIT 1"
        with self._conn() as con:
            row = con.execute(sql, params).fetchone()
        return row is not None

    def list_projects(self, owner_id: str = "legacy") -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute("SELECT * FROM projects WHERE owner_id = ? ORDER BY updated_at DESC", (owner_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_project(self, project_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
        with self._conn() as con:
            if owner_id is None:
                row = con.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            else:
                row = con.execute("SELECT * FROM projects WHERE id = ? AND owner_id = ?", (project_id, owner_id)).fetchone()
            if not row:
                return None
            
            # Join with sources to get the source name if available
            files = con.execute(
                """
                SELECT pf.*, s.name as source_name 
                FROM project_files pf 
                LEFT JOIN sources s ON pf.source_id = s.id 
                WHERE pf.project_id = ? 
                ORDER BY pf.created_at ASC
                """,
                (project_id,),
            ).fetchall()
        
        project = dict(row)
        project["files"] = [dict(f) for f in files]
        return project

    def update_project(self, project_id: str, title: str, owner_id: str = "legacy") -> dict[str, Any] | None:
        clean_title = title.strip()
        if self.project_title_exists(clean_title, owner_id=owner_id, exclude_project_id=project_id):
            raise ValueError("A project with this name already exists")
        now = time.time()
        with self._conn() as con:
            cur = con.execute(
                "UPDATE projects SET title = ?, updated_at = ? WHERE id = ? AND owner_id = ?",
                (clean_title, now, project_id, owner_id),
            )
            if cur.rowcount == 0:
                return None
        return self.get_project(project_id, owner_id=owner_id)

    def delete_project(self, project_id: str, owner_id: str | None = None) -> None:
        with self._conn() as con:
            if owner_id is None:
                con.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            else:
                con.execute("DELETE FROM projects WHERE id = ? AND owner_id = ?", (project_id, owner_id))

    def get_project_instructions(self, project_id: str) -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute("SELECT instructions_json FROM project_instructions WHERE project_id = ?", (project_id,)).fetchone()
        if not row:
            return None
        return json.loads(row["instructions_json"])

    def upsert_project_instructions(self, project_id: str, instructions: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO project_instructions (project_id, instructions_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                  instructions_json=excluded.instructions_json,
                  updated_at=excluded.updated_at
                """,
                (project_id, json.dumps(instructions, default=str), now),
            )
            con.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
        return {"project_id": project_id, "instructions": instructions, "updated_at": now}

    def rebuild_project_memory(self, project_id: str) -> None:
        project = self.get_project(project_id)
        if not project:
            return
        entries: list[tuple[str, str, str, str, str]] = []
        project_instructions = self.get_project_instructions(project_id)
        if project_instructions:
            entries.append((
                project_id,
                "project_instructions",
                project_id,
                "Project instructions",
                json.dumps(project_instructions, ensure_ascii=False, default=str),
            ))
        for note in self.list_project_notes(project_id):
            entries.append((project_id, "note", note["id"], note["title"], note["content"]))
        for file_rec in project.get("files", []):
            source_id = file_rec.get("source_id")
            if not source_id:
                continue
            source = self.get_source(source_id)
            if source:
                entries.append((
                    project_id,
                    "source",
                    source_id,
                    source.get("name") or source_id,
                    source.get("schema_json") or "",
                ))
            source_instructions = self.get_source_instructions(source_id)
            if source_instructions:
                entries.append((
                    project_id,
                    "source_instructions",
                    source_id,
                    f"{source.get('name') if source else source_id} instructions",
                    json.dumps(source_instructions, ensure_ascii=False, default=str),
                ))
        with self._conn() as con:
            con.execute("DELETE FROM project_memory_fts WHERE project_id = ?", (project_id,))
            con.executemany(
                "INSERT INTO project_memory_fts (project_id, kind, ref_id, title, content) VALUES (?, ?, ?, ?, ?)",
                entries,
            )

    def search_project_memory(self, project_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        terms = [part.strip("*\"'") for part in query.split() if part.strip()]
        clean_query = " OR ".join(repr(part) for part in terms)[:200]
        if not clean_query:
            return []
        with self._conn() as con:
            try:
                rows = con.execute(
                    """
                    SELECT project_id, kind, ref_id, title, content
                    FROM project_memory_fts
                    WHERE project_id = ? AND project_memory_fts MATCH ?
                    LIMIT ?
                    """,
                    (project_id, clean_query, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            if not rows:
                terms = [part.strip("*\"'").lower() for part in query.split() if part.strip()]
                like_clauses = " OR ".join(["LOWER(title) LIKE ? OR LOWER(content) LIKE ?"] * len(terms))
                params: list[Any] = [project_id]
                for term in terms:
                    params.extend([f"%{term}%", f"%{term}%"])
                params.append(limit)
                rows = con.execute(
                    f"""
                    SELECT project_id, kind, ref_id, title, content
                    FROM project_memory_fts
                    WHERE project_id = ? AND ({like_clauses})
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
        return [dict(r) for r in rows]

    def add_file_to_project(
        self,
        project_id: str,
        file_path: str | None,
        source_id: str | None = None,
        sheet_name: str | None = None,
    ) -> dict[str, Any]:
        file_id = f"pfile_{uuid.uuid4().hex[:10]}"
        now = time.time()
        # Backward compatibility:
        # historical call shape was (project_id, file_path, sheet_name). Since source
        # IDs are generated with a src_ prefix, treat a non-src_ third positional value
        # as a legacy sheet name when sheet_name is omitted.
        if source_id and sheet_name is None and not source_id.startswith("src_"):
            sheet_name = source_id
            source_id = None
        # Handle SQLite NOT NULL constraint by defaulting to empty string
        safe_file_path = file_path if file_path is not None else ""
        with self._conn() as con:
            if source_id:
                existing = con.execute(
                    "SELECT 1 FROM project_files WHERE project_id = ? AND source_id = ? LIMIT 1",
                    (project_id, source_id),
                ).fetchone()
                if existing:
                    raise ValueError("This source is already linked to the project")
            elif safe_file_path:
                existing = con.execute(
                    """
                    SELECT 1 FROM project_files
                    WHERE project_id = ? AND file_path = ? AND COALESCE(sheet_name, '') = COALESCE(?, '')
                    LIMIT 1
                    """,
                    (project_id, safe_file_path, sheet_name),
                ).fetchone()
                if existing:
                    raise ValueError("This file is already linked to the project")
            con.execute(
                "INSERT INTO project_files (id, project_id, file_path, source_id, sheet_name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (file_id, project_id, safe_file_path, source_id, sheet_name, now),
            )
            con.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
        return {"id": file_id, "project_id": project_id, "file_path": safe_file_path, "source_id": source_id, "sheet_name": sheet_name, "created_at": now}

    def remove_file_from_project(self, project_id: str, file_id: str) -> None:
        now = time.time()
        with self._conn() as con:
            con.execute("DELETE FROM project_files WHERE id = ? AND project_id = ?", (file_id, project_id))
            con.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))

    def add_project_note(
        self,
        project_id: str,
        title: str,
        content: str,
        source_message_id: str | None = None,
    ) -> dict[str, Any]:
        note_id = f"note_{uuid.uuid4().hex[:10]}"
        now = time.time()
        clean_title = title.strip() or "Saved analysis"
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO project_notes (id, project_id, title, content, source_message_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (note_id, project_id, clean_title, content, source_message_id, now),
            )
            con.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
        return {
            "id": note_id,
            "project_id": project_id,
            "title": clean_title,
            "content": content,
            "source_message_id": source_message_id,
            "created_at": now,
        }

    def list_project_notes(self, project_id: str) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM project_notes WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_project_note(self, project_id: str, note_id: str) -> None:
        now = time.time()
        with self._conn() as con:
            con.execute("DELETE FROM project_notes WHERE id = ? AND project_id = ?", (note_id, project_id))
            con.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))

    def update_chat_project(self, chat_id: str, project_id: str | None, owner_id: str | None = None) -> None:
        with self._conn() as con:
            if owner_id is None:
                con.execute("UPDATE chats SET project_id = ? WHERE id = ?", (project_id, chat_id))
            else:
                con.execute("UPDATE chats SET project_id = ? WHERE id = ? AND owner_id = ?", (project_id, chat_id, owner_id))

    # -- testing -------------------------------------------------------------
    def create_test_suite(self, name: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        suite_id = f"ts_{uuid.uuid4().hex[:10]}"
        now = time.time()
        metadata = metadata or {}
        with self._conn() as con:
            con.execute(
                "INSERT INTO test_suites (id, name, metadata_json, created_at) VALUES (?, ?, ?, ?)",
                (suite_id, name, json.dumps(metadata), now),
            )
        return {"id": suite_id, "name": name, "metadata": metadata, "created_at": now}

    def list_test_suites(self) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT ts.*, 
                       (SELECT COUNT(*) FROM test_queries tq WHERE tq.suite_id = ts.id) as query_count,
                       (SELECT MAX(created_at) FROM test_runs tr WHERE tr.suite_id = ts.id) as last_run_at
                FROM test_suites ts
                ORDER BY ts.created_at DESC
                """
            ).fetchall()
        suites = []
        for row in rows:
            suite = dict(row)
            try:
                suite["metadata"] = json.loads(suite.pop("metadata_json") or "{}")
            except json.JSONDecodeError:
                suite["metadata"] = {}
            suites.append(suite)
        return suites

    def get_test_suite(self, suite_id: str) -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute("SELECT * FROM test_suites WHERE id = ?", (suite_id,)).fetchone()
        if not row:
            return None
        suite = dict(row)
        try:
            suite["metadata"] = json.loads(suite.pop("metadata_json") or "{}")
        except json.JSONDecodeError:
            suite["metadata"] = {}
        return suite

    def add_test_queries(self, suite_id: str, queries: list[dict[str, Any]]) -> None:
        now = time.time()
        entries = [
            (
                f"tq_{uuid.uuid4().hex[:10]}",
                suite_id,
                q["question"],
                q.get("category", "Uncategorized"),
                now,
            )
            for q in queries
        ]
        with self._conn() as con:
            con.executemany(
                "INSERT INTO test_queries (id, suite_id, question, category, created_at) VALUES (?, ?, ?, ?, ?)",
                entries,
            )

    def list_test_queries(self, suite_id: str) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM test_queries WHERE suite_id = ? ORDER BY created_at ASC",
                (suite_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def create_test_run(self, suite_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        run_id = f"tr_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._conn() as con:
            total_count = con.execute(
                "SELECT COUNT(*) as c FROM test_queries WHERE suite_id = ?",
                (suite_id,),
            ).fetchone()["c"]
            con.execute(
                """
                INSERT INTO test_runs (id, suite_id, snapshot_json, status, total_count, completed_count, completed_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, suite_id, json.dumps(snapshot), "running", total_count, 0, None, now),
            )
        return {
            "id": run_id,
            "suite_id": suite_id,
            "snapshot": snapshot,
            "status": "running",
            "total_count": total_count,
            "completed_count": 0,
            "completed_at": None,
            "created_at": now,
        }

    def list_test_runs(self, suite_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM test_runs"
        params = []
        if suite_id:
            query += " WHERE suite_id = ?"
            params.append(suite_id)
        query += " ORDER BY created_at DESC"
        
        runs = []
        with self._conn() as con:
            rows = con.execute(query, params).fetchall()
            for r in rows:
                run = dict(r)
                run["snapshot"] = json.loads(run.pop("snapshot_json") or "{}")
                
                # Get aggregated stats
                stats = con.execute(
                    """
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN lower(grade) = 'pass' THEN 1 ELSE 0 END) as pass,
                        SUM(CASE WHEN lower(grade) = 'fail' THEN 1 ELSE 0 END) as fail,
                        SUM(CASE WHEN lower(grade) = 'partial' THEN 1 ELSE 0 END) as partial,
                        SUM(CASE WHEN lower(grade) = 'error' THEN 1 ELSE 0 END) as error,
                        SUM(CASE WHEN lower(ai_grade) = 'pass' THEN 1 ELSE 0 END) as ai_pass,
                        SUM(CASE WHEN lower(ai_grade) = 'fail' THEN 1 ELSE 0 END) as ai_fail,
                        SUM(CASE WHEN lower(ai_grade) = 'partial' THEN 1 ELSE 0 END) as ai_partial,
                        SUM(CASE WHEN lower(grade) = lower(ai_grade) AND grade IS NOT NULL THEN 1 ELSE 0 END) as consensus
                    FROM test_evaluations
                    WHERE run_id = ?
                    """,
                    (run["id"],)
                ).fetchone()
                
                run["stats"] = dict(stats) if stats else {"total": 0, "pass": 0, "fail": 0, "partial": 0, "error": 0, "ai_pass": 0, "ai_fail": 0, "ai_partial": 0, "consensus": 0}
                run["completed_count"] = int(run.get("completed_count") or run["stats"].get("total") or 0)
                if not run.get("total_count"):
                    run["total_count"] = con.execute(
                        "SELECT COUNT(*) as c FROM test_queries WHERE suite_id = ?",
                        (run["suite_id"],),
                    ).fetchone()["c"]
                runs.append(run)
        return runs

    def update_test_run_progress(self, run_id: str, *, status: str | None = None, completed_at: float | None = None) -> None:
        with self._conn() as con:
            completed_count = con.execute(
                "SELECT COUNT(*) as c FROM test_evaluations WHERE run_id = ?",
                (run_id,),
            ).fetchone()["c"]
            if status is None:
                run = con.execute("SELECT total_count FROM test_runs WHERE id = ?", (run_id,)).fetchone()
                total_count = int(run["total_count"] or 0) if run else 0
                status = "completed" if total_count and completed_count >= total_count else "running"
            con.execute(
                "UPDATE test_runs SET status = ?, completed_count = ?, completed_at = ? WHERE id = ?",
                (status, completed_count, completed_at, run_id),
            )

    def add_test_evaluation(
        self,
        run_id: str,
        query_id: str,
        answer: str | None,
        latency_ms: float | None,
        grade: str | None = None,
        reason: str | None = None,
        trace_id: str | None = None,
    ) -> str:
        eval_id = f"ev_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO test_evaluations (id, run_id, query_id, answer, latency_ms, grade, reason, trace_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (eval_id, run_id, query_id, answer, latency_ms, grade, reason, trace_id, now),
            )
            completed_count = con.execute(
                "SELECT COUNT(*) as c FROM test_evaluations WHERE run_id = ?",
                (run_id,),
            ).fetchone()["c"]
            run = con.execute("SELECT total_count FROM test_runs WHERE id = ?", (run_id,)).fetchone()
            total_count = int(run["total_count"] or 0) if run else 0
            status = "completed" if total_count and completed_count >= total_count else "running"
            completed_at = now if status == "completed" else None
            con.execute(
                "UPDATE test_runs SET completed_count = ?, status = ?, completed_at = ? WHERE id = ?",
                (completed_count, status, completed_at, run_id),
            )
        return eval_id

    def update_test_evaluation_ai_grade(self, eval_id: str, ai_grade: str, ai_reason: str) -> None:
        with self._conn() as con:
            con.execute(
                "UPDATE test_evaluations SET ai_grade = ?, ai_reason = ? WHERE id = ?",
                (ai_grade, ai_reason, eval_id),
            )

    def list_test_evaluations(self, run_id: str) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT te.*, tq.question, tq.category, tq.expected_answer
                FROM test_evaluations te
                JOIN test_queries tq ON te.query_id = tq.id
                WHERE te.run_id = ?
                ORDER BY te.created_at ASC
                """,
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def add_user_feedback(
        self,
        chat_id: str | None,
        message_id: str | None,
        rating: int,
        comment: str | None = None,
        category: str = "feedback",
    ) -> dict[str, Any]:
        feedback_id = f"fb_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO user_feedback (id, chat_id, message_id, rating, category, status, comment, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (feedback_id, chat_id, message_id, rating, category, "open", comment, now),
            )
        return {"id": feedback_id, "chat_id": chat_id, "rating": rating, "category": category, "status": "open", "created_at": now}

    def list_user_feedback(self, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if status:
            clauses.append("uf.status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._conn() as con:
            rows = con.execute(
                f"""
                SELECT
                  uf.*,
                  c.title as chat_title,
                  p.title as project_name,
                  p.id as project_id,
                  m.content as answer,
                  m.trace_id,
                  (
                    SELECT prev.content
                    FROM messages prev
                    WHERE prev.chat_id = uf.chat_id
                      AND prev.role = 'user'
                      AND prev.created_at <= COALESCE(m.created_at, uf.created_at)
                    ORDER BY prev.created_at DESC
                    LIMIT 1
                  ) as question
                FROM user_feedback uf
                LEFT JOIN chats c ON c.id = uf.chat_id
                LEFT JOIN projects p ON p.id = c.project_id
                LEFT JOIN messages m ON m.id = uf.message_id
                {where}
                ORDER BY uf.created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def update_user_feedback_status(self, feedback_id: str, status: str) -> None:
        with self._conn() as con:
            con.execute("UPDATE user_feedback SET status = ? WHERE id = ?", (status, feedback_id))

    def update_test_evaluation(self, evaluation_id: str, grade: str, reason: str | None = None) -> None:
        with self._conn() as con:
            con.execute(
                "UPDATE test_evaluations SET grade = ?, reason = ? WHERE id = ?",
                (grade, reason, evaluation_id),
            )

    # -- insights & logging --------------------------------------------------
    def add_token_usage(
        self,
        project_id: str | None,
        user_id: str | None,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        purpose: str = "chat",
    ) -> None:
        usage_id = f"tok_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO token_usage (id, project_id, user_id, model, purpose, prompt_tokens, completion_tokens, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (usage_id, project_id, user_id, model, purpose, prompt_tokens, completion_tokens, now),
            )

    def list_token_usage_by_project(self) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT 
                  p.title as project_name,
                  p.id as project_id,
                  SUM(tu.prompt_tokens) as prompt_tokens,
                  SUM(tu.completion_tokens) as completion_tokens,
                  SUM(tu.prompt_tokens + tu.completion_tokens) as total_tokens
                FROM projects p
                JOIN token_usage tu ON tu.project_id = p.id
                GROUP BY p.id
                ORDER BY total_tokens DESC
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def list_token_usage_by_purpose(self) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT
                  purpose,
                  SUM(prompt_tokens) as prompt_tokens,
                  SUM(completion_tokens) as completion_tokens,
                  SUM(prompt_tokens + completion_tokens) as total_tokens,
                  COUNT(*) as request_count
                FROM token_usage
                GROUP BY purpose
                ORDER BY total_tokens DESC
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def add_hallucination_log(
        self,
        chat_id: str,
        message_id: str,
        score: float,
        reason: str | None = None,
    ) -> None:
        log_id = f"hal_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO hallucination_logs (id, chat_id, message_id, score, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (log_id, chat_id, message_id, score, reason, now),
            )

    def add_query_loop_metrics(
        self,
        *,
        chat_id: str,
        message_id: str | None,
        question: str,
        route: str,
        round_count: int = 0,
        tool_call_count: int = 0,
        tool_error_count: int = 0,
        thinking_event_count: int = 0,
    ) -> dict[str, Any]:
        metric_id = f"loop_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO query_loop_metrics (
                  id, chat_id, message_id, question, route, round_count,
                  tool_call_count, tool_error_count, thinking_event_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metric_id,
                    chat_id,
                    message_id,
                    question,
                    route,
                    max(0, int(round_count or 0)),
                    max(0, int(tool_call_count or 0)),
                    max(0, int(tool_error_count or 0)),
                    max(0, int(thinking_event_count or 0)),
                    now,
                ),
            )
        return {
            "id": metric_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "question": question,
            "route": route,
            "round_count": max(0, int(round_count or 0)),
            "tool_call_count": max(0, int(tool_call_count or 0)),
            "tool_error_count": max(0, int(tool_error_count or 0)),
            "thinking_event_count": max(0, int(thinking_event_count or 0)),
            "created_at": now,
        }

    def list_query_loop_metrics(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT
                  qlm.*,
                  c.title AS chat_title,
                  p.id AS project_id,
                  p.title AS project_name,
                  m.trace_id
                FROM query_loop_metrics qlm
                LEFT JOIN chats c ON c.id = qlm.chat_id
                LEFT JOIN projects p ON p.id = c.project_id
                LEFT JOIN messages m ON m.id = qlm.message_id
                ORDER BY qlm.tool_call_count DESC, qlm.round_count DESC, qlm.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def query_loop_summary(self) -> dict[str, Any]:
        with self._conn() as con:
            row = con.execute(
                """
                SELECT
                  COUNT(*) AS total_queries,
                  SUM(CASE WHEN tool_call_count >= 3 OR round_count >= 3 THEN 1 ELSE 0 END) AS high_loop_queries,
                  AVG(tool_call_count) AS avg_tool_calls,
                  AVG(round_count) AS avg_rounds,
                  SUM(tool_error_count) AS total_tool_errors
                FROM query_loop_metrics
                """
            ).fetchone()
        return {
            "total_queries": int(row["total_queries"] or 0) if row else 0,
            "high_loop_queries": int(row["high_loop_queries"] or 0) if row else 0,
            "avg_tool_calls": round(float(row["avg_tool_calls"] or 0), 2) if row else 0,
            "avg_rounds": round(float(row["avg_rounds"] or 0), 2) if row else 0,
            "total_tool_errors": int(row["total_tool_errors"] or 0) if row else 0,
        }

    def list_hallucination_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT 
                  hl.*, 
                  m.content as message_content, 
                  m.trace_id,
                  c.title as chat_title,
                  p.title as project_name,
                  p.id as project_id
                FROM hallucination_logs hl
                JOIN messages m ON hl.message_id = m.id
                JOIN chats c ON hl.chat_id = c.id
                LEFT JOIN projects p ON c.project_id = p.id
                ORDER BY hl.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
