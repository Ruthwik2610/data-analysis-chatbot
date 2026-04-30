from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS chats (
  id TEXT PRIMARY KEY,
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
  created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, created_at);

CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
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
  kind TEXT,
  label TEXT,
  config TEXT,
  created_at REAL
);

CREATE TABLE IF NOT EXISTS mcp_connectors (
  id TEXT PRIMARY KEY,
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
"""


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            # Check if project_id column exists in chats (migration)
            try:
                con.execute("ALTER TABLE chats ADD COLUMN project_id TEXT REFERENCES projects(id) ON DELETE SET NULL")
            except sqlite3.OperationalError:
                pass # Column already exists or table doesn't exist yet

            try:
                con.execute("ALTER TABLE project_files ADD COLUMN source_id TEXT REFERENCES sources(id) ON DELETE SET NULL")
            except sqlite3.OperationalError:
                pass

            try:
                con.execute("ALTER TABLE project_files ALTER COLUMN file_path DROP NOT NULL") # SQLite doesn't support this
            except sqlite3.OperationalError:
                # In SQLite, we can't easily drop NOT NULL. 
                # But since we'll always provide at least an empty string or the path, it's fine.
                pass

            con.executescript(SCHEMA)
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

    # -- chats ---------------------------------------------------------------
    def create_chat(self, title: str | None = None) -> dict[str, Any]:
        chat_id = f"chat_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._conn() as con:
            con.execute(
                "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (chat_id, title or "New chat", now, now),
            )
        return {"id": chat_id, "title": title or "New chat", "created_at": now, "updated_at": now}

    def list_chats(self) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT c.id, c.title, c.created_at, c.updated_at,
                       (SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id) AS message_count
                FROM chats c
                ORDER BY c.updated_at DESC
                LIMIT 50
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def get_chat(self, chat_id: str) -> dict[str, Any] | None:
        with self._conn() as con:
            chat_row = con.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
            if not chat_row:
                return None
            messages = con.execute(
                "SELECT id, role, content, payload, created_at FROM messages WHERE chat_id = ? ORDER BY created_at ASC",
                (chat_id,),
            ).fetchall()
        return {
            **dict(chat_row),
            "messages": [
                {
                    "id": m["id"],
                    "role": m["role"],
                    "content": m["content"],
                    "payload": json.loads(m["payload"]) if m["payload"] else None,
                    "created_at": m["created_at"],
                }
                for m in messages
            ],
        }

    def update_chat_title(self, chat_id: str, title: str) -> None:
        with self._conn() as con:
            con.execute(
                "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
                (title, time.time(), chat_id),
            )

    def touch_chat(self, chat_id: str) -> None:
        with self._conn() as con:
            con.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (time.time(), chat_id))

    def delete_chat(self, chat_id: str) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM chats WHERE id = ?", (chat_id,))

    def add_message(self, chat_id: str, role: str, content: str, payload: dict | None = None) -> dict[str, Any]:
        msg_id = f"msg_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._conn() as con:
            con.execute(
                "INSERT INTO messages (id, chat_id, role, content, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (msg_id, chat_id, role, content, json.dumps(payload) if payload else None, now),
            )
            con.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
        return {"id": msg_id, "role": role, "content": content, "payload": payload, "created_at": now}

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
    ) -> None:
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO sources (id, name, kind, rows, schema_json, origin, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(id) DO UPDATE SET
                  name=excluded.name, kind=excluded.kind, rows=excluded.rows,
                  schema_json=excluded.schema_json, origin=excluded.origin
                """,
                (
                    source_id,
                    name,
                    kind,
                    rows,
                    schema_json,
                    json.dumps(origin) if origin else None,
                    time.time(),
                ),
            )

    def list_sources(self) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT id, name, kind, rows, active, created_at FROM sources ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return dict(row) if row else None

    def delete_source(self, source_id: str) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM sources WHERE id = ?", (source_id,))

    def set_active_source(self, source_id: str | None) -> None:
        with self._conn() as con:
            con.execute("UPDATE sources SET active = 0")
            if source_id:
                con.execute("UPDATE sources SET active = 1 WHERE id = ?", (source_id,))

    def get_active_source(self) -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute("SELECT * FROM sources WHERE active = 1").fetchone()
        return dict(row) if row else None

    # -- connectors ----------------------------------------------------------
    def add_connector(self, *, kind: str, label: str, config: dict[str, Any]) -> dict[str, Any]:
        conn_id = f"conn_{uuid.uuid4().hex[:10]}"
        with self._conn() as con:
            con.execute(
                "INSERT INTO connectors (id, kind, label, config, created_at) VALUES (?, ?, ?, ?, ?)",
                (conn_id, kind, label, json.dumps(config), time.time()),
            )
        return {"id": conn_id, "kind": kind, "label": label, "config": config}

    def list_connectors(self) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute("SELECT * FROM connectors ORDER BY created_at DESC").fetchall()
        return [{**dict(r), "config": json.loads(r["config"]) if r["config"] else {}} for r in rows]

    def delete_connector(self, connector_id: str) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM connectors WHERE id = ?", (connector_id,))

    def get_connector(self, connector_id: str) -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute("SELECT * FROM connectors WHERE id = ?", (connector_id,)).fetchone()
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
    ) -> dict[str, Any]:
        now = time.time()
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO mcp_connectors (
                  id, name, description, generated_description, description_status,
                  scope, transport, url, command, args_json, tools_json, status,
                  last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
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

    def get_mcp_connector(self, connector_id: str) -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute("SELECT * FROM mcp_connectors WHERE id = ?", (connector_id,)).fetchone()
        return self._mcp_row_to_dict(row) if row else None

    def list_mcp_connectors(self) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute("SELECT * FROM mcp_connectors ORDER BY updated_at DESC").fetchall()
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

    def allowed_mcp_connector_ids(self, project_id: str | None) -> set[str]:
        with self._conn() as con:
            rows = con.execute("SELECT id FROM mcp_connectors WHERE scope = 'global'").fetchall()
            allowed = {r["id"] for r in rows}
            if project_id:
                project_rows = con.execute(
                    "SELECT connector_id FROM project_mcp_connectors WHERE project_id = ?",
                    (project_id,),
                ).fetchall()
                allowed.update(r["connector_id"] for r in project_rows)
        return allowed

    # -- projects ------------------------------------------------------------
    def create_project(self, title: str) -> dict[str, Any]:
        project_id = f"proj_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._conn() as con:
            con.execute(
                "INSERT INTO projects (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (project_id, title, now, now),
            )
        return {"id": project_id, "title": title, "created_at": now, "updated_at": now}

    def list_projects(self) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
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

    def delete_project(self, project_id: str) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM projects WHERE id = ?", (project_id,))

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

    def update_chat_project(self, chat_id: str, project_id: str | None) -> None:
        with self._conn() as con:
            con.execute("UPDATE chats SET project_id = ? WHERE id = ?", (project_id, chat_id))
