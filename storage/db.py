#!/usr/bin/env python3
from __future__ import annotations

"""
SQLite-backed storage for graph / raw / wiki file trees.

Each "project" captures a full snapshot of the graph/, raw/, and wiki/ directories
with per-file relative paths preserved.  The database supports full CRUD, full‑text
search, directory‑tree reconstruction, and disk import/export.

Usage:
    from storage.db import WikiStorage

    db = WikiStorage("storage/wiki.db")
    pid = db.create_project("my-wiki")
    db.import_directory(pid, "graph")
    db.import_directory(pid, "raw")
    db.import_directory(pid, "wiki")
    db.export_project(pid, "/tmp/restored-wiki")
    db.close()
"""

import hashlib
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_TEXT_EXTENSIONS = {
    ".md", ".json", ".jsonl", ".html", ".txt", ".csv", ".xml",
    ".yaml", ".yml", ".toml", ".py", ".js", ".ts", ".css", ".rst",
}


def _is_text_file(filepath: str | Path) -> bool:
    return Path(filepath).suffix.lower() in _TEXT_EXTENSIONS


class WikiStorage:
    """High-level CRUD wrapper around the SQLite database."""

    def __init__(self, db_path: str | Path = "storage/wiki.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        if SCHEMA_PATH.exists():
            self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ── Project CRUD ──────────────────────────────────────────────────

    def create_project(self, name: str, description: str = "") -> int:
        """Create a new project. Returns the project id."""
        cur = self.conn.execute(
            "INSERT INTO projects (name, description) VALUES (?, ?)",
            (name, description),
        )
        self.conn.commit()
        return cur.lastrowid

    def delete_project(self, project_id: int) -> bool:
        """Delete a project and all its files. Returns True if deleted."""
        cur = self.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def get_project(self, project_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_project_by_name(self, name: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None

    def list_projects(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def rename_project(self, project_id: int, new_name: str) -> bool:
        cur = self.conn.execute(
            "UPDATE projects SET name = ?, updated_at = datetime('now') WHERE id = ?",
            (new_name, project_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def touch_project(self, project_id: int) -> None:
        """Update the project's updated_at timestamp."""
        self.conn.execute(
            "UPDATE projects SET updated_at = datetime('now') WHERE id = ?",
            (project_id,),
        )
        self.conn.commit()

    # ── File CRUD ─────────────────────────────────────────────────────

    @staticmethod
    def _extract_category(relative_path: str) -> str:
        return relative_path.rsplit("/", 1)[0]

    def add_file(
        self,
        project_id: int,
        relative_path: str,
        content: bytes | str,
    ) -> int:
        """Add or replace a file.  Returns the file id."""
        relative_path = relative_path.replace("\\", "/")
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        file_name = Path(relative_path).name
        category = self._extract_category(relative_path)
        file_size = len(content_bytes)
        checksum = hashlib.sha256(content_bytes).hexdigest()

        content_text: str | None = None
        if _is_text_file(relative_path):
            content_text = content if isinstance(content, str) else content_bytes.decode("utf-8", errors="replace")

        cur = self.conn.execute(
            """INSERT INTO files (project_id, category, relative_path, file_name,
                                  content, content_text, file_size, checksum)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(project_id, relative_path) DO UPDATE SET
                 category     = excluded.category,
                 content      = excluded.content,
                 content_text = excluded.content_text,
                 file_size    = excluded.file_size,
                 checksum     = excluded.checksum,
                 updated_at   = datetime('now')""",
            (project_id, category, relative_path, file_name, content_bytes, content_text, file_size, checksum),
        )
        self.touch_project(project_id)
        self.conn.commit()
        return cur.lastrowid

    def add_file_from_disk(self, project_id: int, filepath: str | Path) -> int:
        """Read a file from disk and store it under its relative path."""
        filepath = Path(filepath)
        content = filepath.read_bytes()
        return self.add_file(project_id, str(filepath), content)

    def get_file(self, file_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT id, project_id, category, relative_path, file_name, content, "
            "content_text, file_size, checksum, created_at, updated_at "
            "FROM files WHERE id = ?",
            (file_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_file_by_path(self, project_id: int, relative_path: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT id, project_id, category, relative_path, file_name, content, "
            "content_text, file_size, checksum, created_at, updated_at "
            "FROM files WHERE project_id = ? AND relative_path = ?",
            (project_id, relative_path),
        ).fetchone()
        return dict(row) if row else None

    def get_file_content(self, file_id: int) -> bytes | None:
        row = self.conn.execute(
            "SELECT content FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        return row["content"] if row else None

    def get_file_content_by_path(self, project_id: int, relative_path: str) -> bytes | None:
        row = self.conn.execute(
            "SELECT content FROM files WHERE project_id = ? AND relative_path = ?",
            (project_id, relative_path),
        ).fetchone()
        return row["content"] if row else None

    def get_file_text_by_path(self, project_id: int, relative_path: str) -> str | None:
        row = self.conn.execute(
            "SELECT content_text FROM files WHERE project_id = ? AND relative_path = ?",
            (project_id, relative_path),
        ).fetchone()
        if row and row["content_text"] is not None:
            return row["content_text"]
        if row:
            return row["content"].decode("utf-8", errors="replace") if row["content"] else None
        return None

    def update_file(self, file_id: int, content: bytes | str) -> bool:
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        existing = self.get_file(file_id)
        if not existing:
            return False

        content_text = None
        if _is_text_file(existing["relative_path"]):
            content_text = content if isinstance(content, str) else content_bytes.decode("utf-8", errors="replace")

        checksum = hashlib.sha256(content_bytes).hexdigest()
        cur = self.conn.execute(
            """UPDATE files SET content = ?, content_text = ?, file_size = ?,
               checksum = ?, updated_at = datetime('now') WHERE id = ?""",
            (content_bytes, content_text, len(content_bytes), checksum, file_id),
        )
        self.touch_project(existing["project_id"])
        self.conn.commit()
        return cur.rowcount > 0

    def update_file_by_path(self, project_id: int, relative_path: str, content: bytes | str) -> bool:
        existing = self.get_file_by_path(project_id, relative_path)
        if not existing:
            return False
        return self.update_file(existing["id"], content)

    def delete_file(self, file_id: int) -> bool:
        row = self.conn.execute("SELECT project_id FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            return False
        pid = row["project_id"]
        cur = self.conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        self.touch_project(pid)
        self.conn.commit()
        return cur.rowcount > 0

    def delete_file_by_path(self, project_id: int, relative_path: str) -> bool:
        cur = self.conn.execute(
            "DELETE FROM files WHERE project_id = ? AND relative_path = ?",
            (project_id, relative_path),
        )
        self.touch_project(project_id)
        self.conn.commit()
        return cur.rowcount > 0

    # ── List / Query ──────────────────────────────────────────────────

    def list_files(
        self,
        project_id: int,
        prefix: str = "",
    ) -> list[dict[str, Any]]:
        """List files under a directory prefix (e.g. 'wiki/' or 'wiki/concepts/')."""
        cols = ("id, project_id, category, relative_path, file_name, "
                "file_size, checksum, created_at, updated_at")
        if prefix:
            rows = self.conn.execute(
                f"SELECT {cols} FROM files WHERE project_id = ? AND relative_path LIKE ? "
                "ORDER BY relative_path",
                (project_id, f"{prefix}%"),
            ).fetchall()
        else:
            rows = self.conn.execute(
                f"SELECT {cols} FROM files WHERE project_id = ? ORDER BY relative_path",
                (project_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_files_by_category(
        self,
        project_id: int,
        category: str,
    ) -> list[dict[str, Any]]:
        """List all files belonging to a top-level category ('graph' / 'raw' / 'wiki')."""
        rows = self.conn.execute(
            "SELECT id, project_id, category, relative_path, file_name, "
            "file_size, checksum, created_at, updated_at "
            "FROM files WHERE project_id = ? AND category = ? "
            "ORDER BY relative_path",
            (project_id, category),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_all_file_paths(self, project_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT relative_path FROM files WHERE project_id = ? ORDER BY relative_path",
            (project_id,),
        ).fetchall()
        return [r["relative_path"] for r in rows]

    def count_files(self, project_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM files WHERE project_id = ?", (project_id,)
        ).fetchone()
        return row["cnt"] if row else 0

    def total_size(self, project_id: int) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(file_size), 0) AS total FROM files WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return row["total"] if row else 0

    # ── Full-text search ──────────────────────────────────────────────

    def search(self, project_id: int, keyword: str) -> list[dict[str, Any]]:
        """Full-text search across file paths and text content."""
        rows = self.conn.execute(
            """SELECT f.id, f.project_id, f.category, f.relative_path, f.file_name,
                      f.file_size, f.checksum, f.created_at, f.updated_at,
                      snippet(files_fts, 1, '<mark>', '</mark>', '…', 60) AS snippet
               FROM files_fts
               JOIN files f ON f.id = files_fts.rowid
               WHERE f.project_id = ? AND files_fts MATCH ?
               ORDER BY rank""",
            (project_id, keyword),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Directory tree ────────────────────────────────────────────────

    def get_directory_tree(self, project_id: int) -> dict[str, Any]:
        """Return a nested dict representing the file tree of a project.

        Example:
            {
              "graph": {
                "graph.json": 123,
                "graph.html": 124,
                ...
              },
              "raw": { ... },
              "wiki": {
                "concepts": { "全面从严治党.md": 125, ... },
                "index.md": 126,
                ...
              }
            }

        Leaf values are file_id integers.
        """
        tree: dict[str, Any] = {}
        rows = self.conn.execute(
            "SELECT id, relative_path FROM files WHERE project_id = ? ORDER BY relative_path",
            (project_id,),
        ).fetchall()

        for row in rows:
            parts = Path(row["relative_path"]).parts
            node = tree
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = row["id"]

        return tree

    def _write_tree(self, project_id: int, output_dir: Path, tree: dict[str, Any]) -> None:
        for name, value in tree.items():
            target = output_dir / name
            if isinstance(value, dict):
                target.mkdir(parents=True, exist_ok=True)
                self._write_tree(project_id, target, value)
            else:
                row = self.conn.execute(
                    "SELECT content FROM files WHERE id = ?", (value,)
                ).fetchone()
                if row and row["content"] is not None:
                    target.write_bytes(row["content"])

    def export_project(self, project_id: int, output_dir: str | Path) -> int:
        """Reconstruct directory structure to disk. Returns number of files written."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        tree = self.get_directory_tree(project_id)
        self._write_tree(project_id, output_dir, tree)
        return self.count_files(project_id)

    # ── Import from disk ──────────────────────────────────────────────

    def import_directory(self, project_id: int, dir_path: str | Path, strip_prefix: bool = True) -> int:
        """Import all files under dir_path into the project.

        If strip_prefix is True, the top-level directory name is kept (e.g.
        importing 'wiki/' preserves paths like 'wiki/index.md').  If False,
        the full absolute/relative path is stored.
        """
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            raise FileNotFoundError(f"Directory not found: {dir_path}")

        count = 0
        for filepath in dir_path.rglob("*"):
            if filepath.is_file():
                if strip_prefix and dir_path.parent != Path("."):
                    rel = str(filepath.relative_to(dir_path.parent))
                else:
                    rel = str(filepath)
                self.add_file_from_disk(project_id, rel)
                count += 1
        return count

    def import_project_from_disk(self, project_name: str, root: str | Path | None = None) -> int:
        """Create a project and import graph/, raw/, wiki/ from the given root.

        If root is None, REPO_ROOT is used.
        """
        root = Path(root) if root else REPO_ROOT
        pid = self.create_project(project_name, f"Imported from {root}")

        for subdir in ("graph", "raw", "wiki"):
            d = root / subdir
            if d.is_dir():
                self.import_directory(pid, d)

        return pid

    # ── Diff helpers ──────────────────────────────────────────────────

    def diff_checksums(self, project_id: int) -> list[dict[str, Any]]:
        """Compare stored checksums against files currently on disk (relative to REPO_ROOT)."""
        changed: list[dict[str, Any]] = []
        rows = self.conn.execute(
            "SELECT id, relative_path, checksum FROM files WHERE project_id = ?",
            (project_id,),
        ).fetchall()

        for row in rows:
            disk_path = REPO_ROOT / row["relative_path"]
            if disk_path.is_file():
                disk_checksum = hashlib.sha256(disk_path.read_bytes()).hexdigest()
                if disk_checksum != row["checksum"]:
                    changed.append({
                        "file_id": row["id"],
                        "relative_path": row["relative_path"],
                        "db_checksum": row["checksum"],
                        "disk_checksum": disk_checksum,
                    })
            else:
                changed.append({
                    "file_id": row["id"],
                    "relative_path": row["relative_path"],
                    "db_checksum": row["checksum"],
                    "disk_checksum": None,
                    "missing_on_disk": True,
                })
        return changed

    # ── Stats ─────────────────────────────────────────────────────────

    def project_stats(self, project_id: int) -> dict[str, Any]:
        """Return summary stats for a project."""
        proj = self.get_project(project_id)
        file_count = self.count_files(project_id)
        total_bytes = self.total_size(project_id)

        rows = self.conn.execute(
            "SELECT category, COUNT(*) AS cnt FROM files WHERE project_id = ? "
            "GROUP BY category ORDER BY category",
            (project_id,),
        ).fetchall()
        by_category = {r["category"]: r["cnt"] for r in rows}

        return {
            "project": proj,
            "file_count": file_count,
            "total_bytes": total_bytes,
            "by_category": by_category,
        }


def main() -> None:
    """Quick smoke-test / demo."""
    db_path = REPO_ROOT / "storage" / "wiki.db"
    if db_path.exists():
        db_path.unlink()

    db = WikiStorage(db_path)

    pid = db.import_project_from_disk("test-project")
    print(f"Created project #{pid}")

    stats = db.project_stats(pid)
    print(f"  Files: {stats['file_count']}, Size: {stats['total_bytes']} bytes")
    print(f"  By category: {stats['by_category']}")

    all_paths = db.list_all_file_paths(pid)
    print(f"  Sample paths: {all_paths[:5]}...")

    wiki_path = all_paths[0]
    text = db.get_file_text_by_path(pid, wiki_path)
    if text:
        print(f"  First 80 chars of {wiki_path}: {text[:80]}...")

    tree = db.get_directory_tree(pid)
    print(f"  Top-level dirs in tree: {list(tree.keys())}")

    results = db.search(pid, "wiki")
    print(f"  Search 'wiki' → {len(results)} results")

    db.close()
    print("Done.")


if __name__ == "__main__":
    main()