"""Tiny SQLite persistence layer (no ORM, no external service)."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import DB_PATH


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def uid(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:12]


SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
  id TEXT PRIMARY KEY, title TEXT, path TEXT, source_url TEXT,
  duration REAL DEFAULT 0, width INTEGER DEFAULT 0, height INTEGER DEFAULT 0,
  thumbnail TEXT, playlist_id TEXT, metadata TEXT DEFAULT '{}', created_at TEXT
);
CREATE TABLE IF NOT EXISTS playlists (
  id TEXT PRIMARY KEY, url TEXT, title TEXT, items TEXT DEFAULT '[]', created_at TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, kind TEXT, status TEXT, progress REAL DEFAULT 0,
  message TEXT DEFAULT '', payload TEXT DEFAULT '{}', result TEXT,
  error TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, name TEXT, data TEXT DEFAULT '{}',
  created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS clips (
  id TEXT PRIMARY KEY, project_id TEXT, media_id TEXT,
  start REAL, end REAL, score REAL DEFAULT 0, title TEXT, reason TEXT,
  status TEXT DEFAULT 'proposed', output TEXT, metadata TEXT DEFAULT '{}', created_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS analyses (
  id TEXT PRIMARY KEY, media_id TEXT, kind TEXT, data TEXT DEFAULT '{}', created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_analyses_media ON analyses(media_id, kind);
CREATE INDEX IF NOT EXISTS idx_clips_media ON clips(media_id);
"""


class Database:
    def __init__(self, path=DB_PATH):
        self.path = str(path)
        self._lock = threading.RLock()
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(sql, params)

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def insert(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        keys = list(values)
        sql = f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})"
        self.execute(sql, tuple(values[k] for k in keys))
        return values

    def update(self, table: str, key: str, value: str, values: dict[str, Any]) -> None:
        if not values:
            return
        sets = ",".join(f"{k}=?" for k in values)
        self.execute(f"UPDATE {table} SET {sets} WHERE {key}=?", (*values.values(), value))

    def delete(self, table: str, key: str, value: str) -> None:
        self.execute(f"DELETE FROM {table} WHERE {key}=?", (value,))

    # typed convenience -------------------------------------------------
    @staticmethod
    def loads(row: dict[str, Any] | None, *fields: str) -> dict[str, Any] | None:
        if row is None:
            return None
        for field in fields:
            raw = row.get(field)
            if isinstance(raw, str):
                try:
                    row[field] = json.loads(raw)
                except json.JSONDecodeError:
                    row[field] = {}
        return row

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def all_settings(self) -> dict[str, str]:
        return {row["key"]: row["value"] for row in self.query("SELECT key,value FROM settings")}


db = Database()


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
