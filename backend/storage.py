from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
  id TEXT PRIMARY KEY,
  title TEXT,
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
"""


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
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
