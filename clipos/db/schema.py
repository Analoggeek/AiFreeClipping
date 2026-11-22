"""SQLite schema for CLIPOS.

Everything the user creates -- projects, transcripts, generated clips, exports -- lives
in a single local SQLite file.  No cloud, no accounts, no telemetry.
"""
from __future__ import annotations

SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_info (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    description   TEXT    NOT NULL DEFAULT '',
    source_path   TEXT    NOT NULL DEFAULT '',
    source_type   TEXT    NOT NULL DEFAULT 'local',   -- local | url
    source_url    TEXT    NOT NULL DEFAULT '',
    duration      REAL    NOT NULL DEFAULT 0,
    width         INTEGER NOT NULL DEFAULT 0,
    height        INTEGER NOT NULL DEFAULT 0,
    fps           REAL    NOT NULL DEFAULT 0,
    has_audio     INTEGER NOT NULL DEFAULT 0,
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    thumbnail     TEXT    NOT NULL DEFAULT '',
    status        TEXT    NOT NULL DEFAULT 'imported', -- imported|analyzing|ready|error
    aspect_ratio  TEXT    NOT NULL DEFAULT '9:16',
    clip_count    INTEGER NOT NULL DEFAULT 10,
    duration_range TEXT   NOT NULL DEFAULT '30-45',
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    last_opened   TEXT,
    archived      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transcripts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    language    TEXT NOT NULL DEFAULT 'en',
    model       TEXT NOT NULL DEFAULT '',
    duration    REAL NOT NULL DEFAULT 0,
    full_text   TEXT NOT NULL DEFAULT '',
    segments    TEXT NOT NULL DEFAULT '[]',   -- JSON: [{start,end,text,words:[...]}]
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_transcripts_project ON transcripts(project_id);

CREATE TABLE IF NOT EXISTS clips (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id        INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title             TEXT    NOT NULL DEFAULT '',
    description       TEXT    NOT NULL DEFAULT '',
    start_time        REAL    NOT NULL DEFAULT 0,
    end_time          REAL    NOT NULL DEFAULT 0,
    duration          REAL    NOT NULL DEFAULT 0,
    engagement_score  REAL    NOT NULL DEFAULT 0,   -- 0..100 AI ranking
    virality_score    REAL    NOT NULL DEFAULT 0,   -- 0..100 virality potential
    reason            TEXT    NOT NULL DEFAULT '',
    transcript_text   TEXT    NOT NULL DEFAULT '',
    hook_suggestions  TEXT    NOT NULL DEFAULT '[]', -- JSON list[str]
    keywords          TEXT    NOT NULL DEFAULT '[]', -- JSON list[str]
    hashtags          TEXT    NOT NULL DEFAULT '[]', -- JSON list[str]
    titles            TEXT    NOT NULL DEFAULT '[]', -- JSON list[str] (5 alternatives)
    thumbnail_path    TEXT    NOT NULL DEFAULT '',
    output_path       TEXT    NOT NULL DEFAULT '',
    aspect_ratio      TEXT    NOT NULL DEFAULT '9:16',
    caption_style     TEXT    NOT NULL DEFAULT 'bold_viral',
    status            TEXT    NOT NULL DEFAULT 'pending', -- pending|editing|rendered|exported|error
    edited            INTEGER NOT NULL DEFAULT 0,
    settings          TEXT    NOT NULL DEFAULT '{}',
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_clips_project ON clips(project_id);

CREATE TABLE IF NOT EXISTS captions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id    INTEGER NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    style      TEXT NOT NULL DEFAULT 'bold_viral',
    cues       TEXT NOT NULL DEFAULT '[]',  -- JSON: [{start,end,text,words:[{w,s,e}]}]
    font       TEXT NOT NULL DEFAULT '',
    size       INTEGER NOT NULL DEFAULT 58,
    position   TEXT NOT NULL DEFAULT 'bottom',
    stroke     INTEGER NOT NULL DEFAULT 4,
    shadow     INTEGER NOT NULL DEFAULT 1,
    background INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_captions_clip ON captions(clip_id);

CREATE TABLE IF NOT EXISTS exports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    clip_id     INTEGER REFERENCES clips(id) ON DELETE SET NULL,
    output_path TEXT NOT NULL DEFAULT '',
    format      TEXT NOT NULL DEFAULT 'mp4',
    width       INTEGER NOT NULL DEFAULT 1080,
    height      INTEGER NOT NULL DEFAULT 1920,
    fps         INTEGER NOT NULL DEFAULT 30,
    codec       TEXT NOT NULL DEFAULT 'h264',
    bitrate     INTEGER NOT NULL DEFAULT 8000,
    size_bytes  INTEGER NOT NULL DEFAULT 0,
    duration    REAL NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'pending', -- pending|rendering|done|error|cancelled
    error       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_exports_project ON exports(project_id);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS models (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL DEFAULT '',
    kind         TEXT NOT NULL DEFAULT '',   -- stt | llm | cv | embed
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    installed    INTEGER NOT NULL DEFAULT 0,
    enabled      INTEGER NOT NULL DEFAULT 1,
    downloaded_at TEXT,
    source       TEXT NOT NULL DEFAULT '',
    sha256       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS activity (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    kind       TEXT NOT NULL DEFAULT '',
    message    TEXT NOT NULL DEFAULT '',
    level      TEXT NOT NULL DEFAULT 'info',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity(created_at DESC);

CREATE TABLE IF NOT EXISTS app_errors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    context    TEXT NOT NULL DEFAULT '',
    message    TEXT NOT NULL DEFAULT '',
    traceback  TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
