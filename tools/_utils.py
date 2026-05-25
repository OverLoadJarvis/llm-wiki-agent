#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import sys
import hashlib
from pathlib import Path

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

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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
    return path.relative_to(WIKI_DIR).as_posix().replace(".md", "")


def page_stem_set() -> set[str]:
    return {p.stem.lower() for p in all_wiki_pages()}


def append_log(entry: str):
    existing = read_file(LOG_FILE)
    LOG_FILE.write_text(entry.strip() + "\n\n" + existing, encoding="utf-8")