from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "travel.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS traveler_profiles (
  id TEXT PRIMARY KEY,
  client_name TEXT NOT NULL UNIQUE,
  preferred_airline TEXT,
  meal_preference TEXT,
  visa_country_held TEXT,
  visa_expiration_date TEXT,
  approved_cabin_class TEXT,
  timing_preference TEXT,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_traveler_profiles_name ON traveler_profiles(client_name);
"""


class TravelStorage:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            conn.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert_traveler_profile(self, profile: dict) -> dict:
        client_name = (profile.get("client_name") or "").strip()
        if not client_name:
            raise ValueError("client_name is required and must not be empty")

        now = time.time()
        row_id = f"prof_{uuid.uuid4().hex[:10]}"

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO traveler_profiles
                  (id, client_name, preferred_airline, meal_preference,
                   visa_country_held, visa_expiration_date, approved_cabin_class,
                   timing_preference, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_name) DO UPDATE SET
                  preferred_airline    = excluded.preferred_airline,
                  meal_preference      = excluded.meal_preference,
                  visa_country_held    = excluded.visa_country_held,
                  visa_expiration_date = excluded.visa_expiration_date,
                  approved_cabin_class = excluded.approved_cabin_class,
                  timing_preference    = excluded.timing_preference,
                  updated_at           = excluded.updated_at
                """,
                (
                    row_id,
                    client_name,
                    profile.get("preferred_airline"),
                    profile.get("meal_preference"),
                    profile.get("visa_country_held"),
                    profile.get("visa_expiration_date"),
                    profile.get("approved_cabin_class"),
                    profile.get("timing_preference"),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM traveler_profiles WHERE client_name = ?", (client_name,)
            ).fetchone()
        return dict(row)

    def get_by_name(self, client_name: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM traveler_profiles WHERE client_name = ?", (client_name,)
            ).fetchone()
        return dict(row) if row else None

    def list_all(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM traveler_profiles ORDER BY client_name"
            ).fetchall()
        return [dict(r) for r in rows]
