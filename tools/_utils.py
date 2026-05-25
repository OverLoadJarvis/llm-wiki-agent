#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import sys
import hashlib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
RAW_DIR = REPO_ROOT / "raw"
GRAPH_DIR = REPO_ROOT / "graph"
INDEX_FILE = WIKI_DIR / "index.md"
LOG_FILE = WIKI_DIR / "log.md"
OVERVIEW_FILE = WIKI_DIR / "overview.md"
SCHEMA_FILE = REPO_ROOT / "FORMATS.md"
SOURCES_DIR = WIKI_DIR / "sources"
ENTITIES_DIR = WIKI_DIR / "entities"
CONCEPTS_DIR = WIKI_DIR / "concepts"
SYNTHESES_DIR = WIKI_DIR / "syntheses"
GRAPH_JSON = GRAPH_DIR / "graph.json"

META_PAGES = {"index.md", "log.md", "lint-report.md", "health-report.md"}

_db: Any = None
_project_id: int | None = None

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass


def use_storage(db, project_id: int):
    global _db, _project_id
    _db = db
    _project_id = project_id


def is_db_mode() -> bool:
    return _db is not None and _project_id is not None


def get_storage():
    return _db, _project_id


def _to_db_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def read_file(path: Path) -> str:
    if _db is not None:
        rel = _to_db_path(path)
        content = _db.get_file_text_by_path(_project_id, rel)
        return content or ""
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_file(path: Path, content: str):
    if _db is not None:
        rel = _to_db_path(path)
        _db.add_file(_project_id, rel, content)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_file_bytes(path: Path) -> bytes:
    if _db is not None:
        rel = _to_db_path(path)
        content = _db.get_file_content_by_path(_project_id, rel)
        return content or b""
    return path.read_bytes() if path.exists() else b""


def file_exists(path: Path) -> bool:
    if _db is not None:
        rel = _to_db_path(path)
        return _db.get_file_by_path(_project_id, rel) is not None
    return path.exists()


def file_mtime(path: Path) -> float:
    if _db is not None:
        rel = _to_db_path(path)
        f = _db.get_file_by_path(_project_id, rel)
        if f:
            from datetime import datetime
            dt_str = f.get("updated_at", "1970-01-01")
            try:
                return datetime.fromisoformat(dt_str).timestamp()
            except (ValueError, TypeError):
                return 0
        return 0
    return path.stat().st_mtime if path.exists() else 0


def delete_file(path: Path):
    if _db is not None:
        rel = _to_db_path(path)
        _db.delete_file_by_path(_project_id, rel)
        return
    if path.exists():
        path.unlink()


def ensure_dir(path: Path):
    if _db is not None:
        return
    path.mkdir(parents=True, exist_ok=True)


def list_dir(path: Path, pattern: str = "*.md") -> list[Path]:
    if _db is not None:
        prefix = _to_db_path(path)
        files = _db.list_files(_project_id, prefix=prefix)
        import fnmatch
        return [Path(f["relative_path"]) for f in files
                if fnmatch.fnmatch(f["file_name"], pattern)]
    return list(path.glob(pattern))


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def call_llm(prompt: str, model_env: str | None = None, default_model: str | None = None, max_tokens: int = 4096) -> str:
    try:
        from litellm import completion
    except ImportError:
        print("Error: litellm not installed. Run: pip install litellm")
        sys.exit(1)

    if model_env and default_model:
        model = os.getenv(model_env, default_model)
    else:
        model = os.getenv("LLM_MODEL", "claude-3-5-sonnet-latest")

    kwargs: dict = {
        "model": model,
        "messages": [{"role": "system", "content": prompt}],
    }

    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    api_base = os.getenv("OPENAI_API_BASE")
    api_key = os.getenv("OPENAI_API_KEY")

    if api_base:
        kwargs["api_base"] = api_base
    if api_key:
        kwargs["api_key"] = api_key

    response = completion(**kwargs)
    return response.choices[0].message.content


def all_wiki_pages() -> list[Path]:
    if _db is not None:
        files = _db.list_files(_project_id, prefix="wiki/")
        return [Path(f["relative_path"]) for f in files
                if f["file_name"] not in META_PAGES]
    return [p for p in WIKI_DIR.rglob("*.md") if p.name not in META_PAGES]


def extract_wikilinks(content: str) -> list[str]:
    return re.findall(r"\[\[([^\]]+)\]\]", content)


def extract_wikilinks_unique(content: str) -> list[str]:
    return list(set(extract_wikilinks(content)))


def extract_frontmatter_type(content: str) -> str:
    match = re.search(r"^type:\s*(\S+)", content, re.MULTILINE)
    return match.group(1).strip("\"'") if match else "unknown"


def extract_frontmatter_title(content: str) -> str | None:
    match = re.search(r'^title:\s*"?([^"\n]+)"?', content, re.MULTILINE)
    return match.group(1).strip() if match else None


def strip_frontmatter(content: str) -> str:
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[end + 3:].strip()
    return content.strip()


def page_id(path: Path) -> str:
    try:
        return path.relative_to(WIKI_DIR).as_posix().replace(".md", "")
    except ValueError:
        rel = path.as_posix()
        if rel.startswith("wiki/"):
            return rel[5:].replace(".md", "")
        return rel.replace(".md", "")


def page_stem_set() -> set[str]:
    if _db is not None:
        files = _db.list_files(_project_id, prefix="wiki/")
        return {Path(f["relative_path"]).stem.lower() for f in files
                if f["file_name"] not in META_PAGES}
    return {p.stem.lower() for p in all_wiki_pages()}


def append_log(entry: str):
    existing = read_file(LOG_FILE)
    if _db is not None:
        write_file(LOG_FILE, entry.strip() + "\n\n" + (existing or ""))
        return
    LOG_FILE.write_text(entry.strip() + "\n\n" + existing, encoding="utf-8")
