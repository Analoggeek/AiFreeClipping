"""SQLite access layer for CLIPOS.

A single connection-per-thread with WAL mode so the UI never blocks on disk writes.
All queries are parameterised; nothing is interpolated.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..core.config import DEFAULT_SETTINGS, PATHS
from ..core.logging_setup import get_logger
from .schema import SCHEMA, SCHEMA_VERSION

log = get_logger(__name__)



def _coerce_setting(raw: Any, default: Any) -> Any:
    """Convert a stored setting string back to the type of its default."""
    if raw is None:
        return default
    if default is None:
        return raw
    if isinstance(default, bool):
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(float(str(raw).strip()))
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        try:
            return float(str(raw).strip())
        except (TypeError, ValueError):
            return default
    return raw


class Database:
    """Thread-safe SQLite wrapper scoped to one database file."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else PATHS.db_path
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self._init_schema()

    # -- connection handling -----------------------------------------------------
    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.path), timeout=30.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn = conn
        return conn

    def _init_schema(self) -> None:
        conn = self.conn
        with self._write_lock:
            conn.executescript(SCHEMA)
            self._migrate(conn)
            conn.execute(
                "INSERT INTO schema_info(key, value) VALUES('version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )
            conn.commit()

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Add columns introduced after a user's DB was first created.

        ``executescript`` only creates missing tables; it never adds columns to an
        existing table.  These ALTERs keep older databases working.
        """
        additions = {
            "projects": [
                ("size_bytes", "INTEGER NOT NULL DEFAULT 0"),
            ],
            "clips": [
                ("virality_score", "REAL NOT NULL DEFAULT 0"),
                ("hook_suggestions", "TEXT NOT NULL DEFAULT '[]'"),
            ],
        }
        for table, cols in additions.items():
            try:
                existing = {
                    r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
                }
            except sqlite3.Error:
                continue
            if not existing:
                continue
            for col, ddl in cols:
                if col not in existing:
                    try:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                    except sqlite3.Error as exc:
                        log.warning("migration %s.%s failed: %s", table, col, exc)

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # -- generic helpers ---------------------------------------------------------
    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return list(self.conn.execute(sql, tuple(params)).fetchall())

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, tuple(params)).fetchone()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self._write_lock:
            cur = self.conn.execute(sql, tuple(params))
            self.conn.commit()
            return cur.lastrowid if cur.lastrowid is not None else cur.rowcount

    def execute_many(self, sql: str, seq: Iterable[Sequence[Any]]) -> None:
        with self._write_lock:
            self.conn.executemany(sql, [tuple(s) for s in seq])
            self.conn.commit()

    def executemany_returning(self, sql: str, seq: Iterable[Sequence[Any]]) -> list[int]:
        ids: list[int] = []
        with self._write_lock:
            cur = self.conn.executemany(sql, [tuple(s) for s in seq])
            self.conn.commit()
            ids = list(cur.lastrowid or [])
        return ids

    @contextmanager
    def transaction(self):
        with self._write_lock:
            try:
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    # -- settings ---------------------------------------------------------------
    def get_settings(self) -> dict:
        """Return every setting, with values converted back to their real type.

        Settings are stored as text in SQLite, so the value is coerced using the
        type of the default.  Without this a setting saved as ``-32.0`` would
        come back as the string ``"-32.0"`` and break any caller that expects
        a number.
        """
        rows = self.query("SELECT key, value FROM settings")
        stored = {r["key"]: r["value"] for r in rows}
        merged = dict(DEFAULT_SETTINGS)
        for key, raw in stored.items():
            merged[key] = _coerce_setting(raw, DEFAULT_SETTINGS.get(key))
        # Always keep output_dir pointing at a real path
        merged["output_dir"] = str(merged.get("output_dir") or PATHS.exports)
        return merged

    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self.query_one("SELECT value FROM settings WHERE key=?", (key,))
        if row is None:
            return DEFAULT_SETTINGS.get(key, default)
        fallback = DEFAULT_SETTINGS.get(key, default)
        return _coerce_setting(row["value"], fallback)

    def set_setting(self, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )

    def set_settings(self, values: dict) -> None:
        with self._write_lock:
            self.conn.executemany(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                [(k, str(v)) for k, v in values.items()],
            )
            self.conn.commit()

    def export_settings(self, path: str | Path) -> Path:
        """Write the current settings to a JSON file the user can keep or share."""
        import json
        from pathlib import Path as _Path

        path = _Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "settings": self.get_settings(),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def import_settings(self, path: str | Path) -> int:
        """Load settings from a JSON file produced by :meth:`export_settings`.

        Returns the number of settings applied.  Unknown keys are ignored so a
        file exported from a newer build still loads.
        """
        import json
        from pathlib import Path as _Path

        path = _Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        values = data.get("settings") if isinstance(data, dict) else None
        if not isinstance(values, dict):
            raise ValueError("That file does not contain CLIPOS settings")

        known = set(DEFAULT_SETTINGS)
        applied = {k: v for k, v in values.items() if k in known}
        if applied:
            self.set_settings(applied)
        return len(applied)

    # -- recovery ----------------------------------------------------------------
    def find_interrupted_projects(self) -> list[sqlite3.Row]:
        """Projects that were left mid-task by a crash or a forced quit.

        These are the projects a user would want to resume: they were being
        analysed or exported when the application stopped.
        """
        return self.query(
            "SELECT * FROM projects WHERE status IN ('analyzing', 'exporting', 'rendering') "
            "ORDER BY updated_at DESC"
        )

    def recover_projects(self) -> list[sqlite3.Row]:
        """Reset projects that were interrupted and report what was recovered.

        A project whose source file is gone cannot be recovered; it is marked
        as ``error`` so the UI can explain why.  One whose source file is
        present goes back to ``imported`` and is ready to re-analyse.
        """
        recovered: list[sqlite3.Row] = []
        for row in self.find_interrupted_projects():
            source = row["source_path"]
            if source and Path(source).exists():
                self.update_project(row["id"], status="imported")
                recovered.append(self.get_project(row["id"]))
            else:
                self.update_project(row["id"], status="error")
                recovered.append(self.get_project(row["id"]))
        if recovered:
            self.log_activity(
                None, "recovery",
                f"Recovered {len(recovered)} interrupted project(s)",
                level="warning",
            )
        return recovered

    # -- projects ----------------------------------------------------------------
    PROJECT_DEFAULTS = {
        "description": "", "source_path": "", "source_type": "local", "source_url": "",
        "duration": 0.0, "width": 0, "height": 0, "fps": 0.0, "has_audio": 0,
        "size_bytes": 0,
        "thumbnail": "", "status": "imported", "aspect_ratio": "9:16",
        "clip_count": 10, "duration_range": "30-45",
    }

    def create_project(self, **fields) -> int:
        cols = [
            "name", "description", "source_path", "source_type", "source_url",
            "duration", "width", "height", "fps", "has_audio", "size_bytes", "thumbnail",
            "status", "aspect_ratio", "clip_count", "duration_range",
        ]
        vals = [fields.get(c, self.PROJECT_DEFAULTS.get(c, "")) for c in cols]
        placeholders = ",".join("?" for _ in cols)
        pid = self.execute(
            f"INSERT INTO projects({','.join(cols)}) VALUES({placeholders})", vals
        )
        self.log_activity(pid, "project", f"Created project '{fields.get('name')}'")
        return pid

    def update_project(self, project_id: int, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = "datetime('now')"
        sets = []
        params: list[Any] = []
        for k, v in fields.items():
            if k == "updated_at":
                sets.append("updated_at=datetime('now')")
                continue
            sets.append(f"{k}=?")
            params.append(v)
        params.append(project_id)
        self.execute(f"UPDATE projects SET {','.join(sets)} WHERE id=?", params)

    def delete_project(self, project_id: int) -> None:
        self.execute("DELETE FROM projects WHERE id=?", (project_id,))

    def get_project(self, project_id: int) -> sqlite3.Row | None:
        return self.query_one("SELECT * FROM projects WHERE id=?", (project_id,))

    def list_projects(self, include_archived: bool = False) -> list[sqlite3.Row]:
        q = "SELECT * FROM projects"
        if not include_archived:
            q += " WHERE archived=0"
        q += " ORDER BY COALESCE(last_opened, updated_at) DESC, id DESC"
        return self.query(q)

    def duplicate_project(self, project_id: int) -> int | None:
        src = self.get_project(project_id)
        if not src:
            return None
        new_id = self.create_project(**{
            "name": f"{src['name']} (copy)",
            "description": src["description"],
            "source_path": src["source_path"],
            "source_type": src["source_type"],
            "source_url": src["source_url"],
            "duration": src["duration"],
            "width": src["width"],
            "height": src["height"],
            "fps": src["fps"],
            "has_audio": src["has_audio"],
            "size_bytes": src["size_bytes"],
            "thumbnail": src["thumbnail"],
            "status": "imported",
            "aspect_ratio": src["aspect_ratio"],
            "clip_count": src["clip_count"],
            "duration_range": src["duration_range"],
        })
        tr = self.query_one("SELECT * FROM transcripts WHERE project_id=?", (project_id,))
        if tr:
            self.execute(
                "INSERT INTO transcripts(project_id, language, model, duration, full_text, segments) "
                "VALUES(?,?,?,?,?,?)",
                (new_id, tr["language"], tr["model"], tr["duration"], tr["full_text"], tr["segments"]),
            )
        clips = self.query("SELECT * FROM clips WHERE project_id=?", (project_id,))
        for c in clips:
            self.execute(
                "INSERT INTO clips(project_id, title, description, start_time, end_time, duration,"
                " engagement_score, virality_score, reason, transcript_text, hook_suggestions,"
                " keywords, hashtags, titles, thumbnail_path, output_path, aspect_ratio,"
                " caption_style, status, edited, settings)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    new_id, c["title"], c["description"], c["start_time"], c["end_time"], c["duration"],
                    c["engagement_score"], c["virality_score"], c["reason"], c["transcript_text"],
                    c["hook_suggestions"], c["keywords"], c["hashtags"], c["titles"],
                    c["thumbnail_path"], c["output_path"], c["aspect_ratio"], c["caption_style"],
                    "pending", 0, c["settings"],
                ),
            )
        return new_id

    # -- transcripts --------------------------------------------------------------
    def save_transcript(
        self, project_id: int, language: str, model: str, duration: float,
        full_text: str, segments: list[dict],
    ) -> int:
        self.execute("DELETE FROM transcripts WHERE project_id=?", (project_id,))
        return self.execute(
            "INSERT INTO transcripts(project_id, language, model, duration, full_text, segments)"
            " VALUES(?,?,?,?,?,?)",
            (project_id, language, model, duration, full_text, json.dumps(segments)),
        )

    def get_transcript(self, project_id: int) -> sqlite3.Row | None:
        return self.query_one(
            "SELECT * FROM transcripts WHERE project_id=? ORDER BY id DESC LIMIT 1",
            (project_id,),
        )

    # -- clips -------------------------------------------------------------------
    CLIP_DEFAULTS = {
        "title": "", "description": "", "start_time": 0.0, "end_time": 0.0, "duration": 0.0,
        "engagement_score": 0.0, "virality_score": 0.0, "reason": "", "transcript_text": "",
        "hook_suggestions": "[]", "keywords": "[]", "hashtags": "[]", "titles": "[]",
        "thumbnail_path": "", "output_path": "", "aspect_ratio": "9:16",
        "caption_style": "bold_viral", "status": "pending", "edited": 0, "settings": "{}",
    }

    def create_clip(self, **fields) -> int:
        cols = [
            "project_id", "title", "description", "start_time", "end_time", "duration",
            "engagement_score", "virality_score", "reason", "transcript_text",
            "hook_suggestions", "keywords", "hashtags", "titles", "thumbnail_path",
            "output_path", "aspect_ratio", "caption_style", "status", "edited", "settings",
        ]
        vals = [fields.get(c, self.CLIP_DEFAULTS.get(c, "")) for c in cols]
        placeholders = ",".join("?" for _ in cols)
        return self.execute(
            f"INSERT INTO clips({','.join(cols)}) VALUES({placeholders})", vals
        )

    def update_clip(self, clip_id: int, **fields) -> None:
        if not fields:
            return
        sets, params = [], []
        for k, v in fields.items():
            sets.append(f"{k}=?")
            params.append(v)
        sets.append("updated_at=datetime('now')")
        params.append(clip_id)
        self.execute(f"UPDATE clips SET {','.join(sets)} WHERE id=?", params)

    def delete_clip(self, clip_id: int) -> None:
        self.execute("DELETE FROM clips WHERE id=?", (clip_id,))

    def get_clip(self, clip_id: int) -> sqlite3.Row | None:
        return self.query_one("SELECT * FROM clips WHERE id=?", (clip_id,))

    def list_clips(self, project_id: int | None = None) -> list[sqlite3.Row]:
        if project_id is None:
            return self.query("SELECT * FROM clips ORDER BY created_at DESC")
        return self.query(
            "SELECT * FROM clips WHERE project_id=? ORDER BY virality_score DESC, start_time ASC",
            (project_id,),
        )

    # -- captions ----------------------------------------------------------------
    def save_captions(self, clip_id: int, cues: list[dict], style: str = "bold_viral",
                      font: str = "", size: int = 58, position: str = "bottom",
                      stroke: int = 4, shadow: bool = True, background: bool = False) -> int:
        self.execute("DELETE FROM captions WHERE clip_id=?", (clip_id,))
        return self.execute(
            "INSERT INTO captions(clip_id, style, cues, font, size, position, stroke, shadow, background)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (clip_id, style, json.dumps(cues), font, size, position, stroke,
             int(shadow), int(background)),
        )

    def get_captions(self, clip_id: int) -> sqlite3.Row | None:
        return self.query_one(
            "SELECT * FROM captions WHERE clip_id=? ORDER BY id DESC LIMIT 1", (clip_id,)
        )

    # -- exports -----------------------------------------------------------------
    def create_export(self, **fields) -> int:
        cols = ["project_id", "clip_id", "output_path", "format", "width", "height",
                "fps", "codec", "bitrate", "size_bytes", "duration", "status", "error"]
        defaults = {"format": "mp4", "width": 1080, "height": 1920, "fps": 30,
                    "codec": "h264", "bitrate": 8000, "duration": 0.0,
                    "size_bytes": 0, "status": "pending", "error": ""}
        vals = [fields.get(c, defaults.get(c)) for c in cols]
        placeholders = ",".join("?" for _ in cols)
        return self.execute(f"INSERT INTO exports({','.join(cols)}) VALUES({placeholders})", vals)

    def update_export(self, export_id: int, **fields) -> None:
        if not fields:
            return
        sets, params = [], []
        for k, v in fields.items():
            sets.append(f"{k}=?")
            params.append(v)
        params.append(export_id)
        self.execute(f"UPDATE exports SET {','.join(sets)} WHERE id=?", params)

    def list_exports(self, project_id: int | None = None, limit: int = 200) -> list[sqlite3.Row]:
        if project_id is None:
            return self.query("SELECT * FROM exports ORDER BY id DESC LIMIT ?", (limit,))
        return self.query(
            "SELECT * FROM exports WHERE project_id=? ORDER BY id DESC LIMIT ?",
            (project_id, limit),
        )

    # -- activity / errors --------------------------------------------------------
    def log_activity(self, project_id: int | None, kind: str, message: str,
                     level: str = "info") -> None:
        self.execute(
            "INSERT INTO activity(project_id, kind, message, level) VALUES(?,?,?,?)",
            (project_id, kind, message, level),
        )

    def recent_activity(self, limit: int = 30) -> list[sqlite3.Row]:
        return self.query(
            "SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,)
        )

    def log_error(self, context: str, message: str, tb: str = "") -> None:
        self.execute(
            "INSERT INTO app_errors(context, message, traceback) VALUES(?,?,?)",
            (context, message, tb[:8000]),
        )

    def clear_errors(self) -> None:
        self.execute("DELETE FROM app_errors")

    def recent_errors(self, limit: int = 50) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM app_errors ORDER BY id DESC LIMIT ?", (limit,))

    # -- statistics ---------------------------------------------------------------
    def stats(self) -> dict:
        def scalar(sql, params=()):
            row = self.query_one(sql, params)
            return row[0] if row and row[0] is not None else 0

        videos = scalar("SELECT COUNT(*) FROM projects")
        shorts = scalar("SELECT COUNT(*) FROM clips")
        exports_done = scalar("SELECT COUNT(*) FROM exports WHERE status='done'")
        storage = scalar("SELECT COALESCE(SUM(size_bytes),0) FROM projects")
        export_storage = scalar("SELECT COALESCE(SUM(size_bytes),0) FROM exports")
        total_duration = scalar("SELECT COALESCE(SUM(duration),0) FROM projects")
        avg_viral = scalar("SELECT COALESCE(AVG(virality_score),0) FROM clips")
        return {
            "projects": videos,
            "clips": shorts,
            "exports": exports_done,
            "storage_bytes": int(storage) + int(export_storage),
            "total_media_seconds": float(total_duration),
            "avg_virality": float(avg_viral),
            "transcripts": scalar("SELECT COUNT(*) FROM transcripts"),
        }

    # -- models -------------------------------------------------------------------
    def upsert_model(self, model_id: str, **fields) -> None:
        existing = self.query_one("SELECT id FROM models WHERE id=?", (model_id,))
        if existing:
            if fields:
                sets = ", ".join(f"{k}=?" for k in fields)
                self.execute(
                    f"UPDATE models SET {sets} WHERE id=?",
                    (*fields.values(), model_id),
                )
        else:
            cols = ["id"] + list(fields.keys())
            vals = [model_id] + list(fields.values())
            self.execute(
                f"INSERT INTO models({','.join(cols)}) VALUES({','.join('?' * len(cols))})", vals
            )

    def list_models(self) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM models ORDER BY kind, name")

    def set_model_enabled(self, model_id: str, enabled: bool) -> None:
        self.execute("UPDATE models SET enabled=? WHERE id=?", (int(enabled), model_id))


_db: Database | None = None


def get_db(path: str | Path | None = None) -> Database:
    global _db
    if _db is None or (path is not None and str(path) != str(_db.path)):
        _db = Database(path)
    return _db
