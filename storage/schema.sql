-- SQLite schema for storing graph / raw / wiki file trees as projects.
-- Each project holds a snapshot of the three directories with full path preservation,
-- enabling search, retrieval, and directory-structure reconstruction.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT    DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL,
    category     TEXT    NOT NULL DEFAULT '', -- parent dir: 'graph', 'wiki/concepts', 'raw' etc.
    relative_path TEXT   NOT NULL,            -- e.g. 'wiki/concepts/全面从严治党.md'
    file_name    TEXT    NOT NULL,             -- basename: '全面从严治党.md'
    content      BLOB,                        -- raw file bytes (text or binary)
    content_text TEXT,                        -- text version for FTS; NULL for pure-binary files
    file_size    INTEGER NOT NULL DEFAULT 0,
    checksum     TEXT,                        -- SHA-256 hex digest
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(project_id, relative_path)
);

CREATE INDEX IF NOT EXISTS idx_files_project  ON files(project_id);
CREATE INDEX IF NOT EXISTS idx_files_path     ON files(project_id, relative_path);
CREATE INDEX IF NOT EXISTS idx_files_category ON files(project_id, category);

CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    relative_path,
    content_text,
    content='files',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
    INSERT INTO files_fts(rowid, relative_path, content_text)
    VALUES (new.id, new.relative_path, new.content_text);
END;

CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, relative_path, content_text)
    VALUES ('delete', old.id, old.relative_path, old.content_text);
END;

CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, relative_path, content_text)
    VALUES ('delete', old.id, old.relative_path, old.content_text);
    INSERT INTO files_fts(rowid, relative_path, content_text)
    VALUES (new.id, new.relative_path, new.content_text);
END;