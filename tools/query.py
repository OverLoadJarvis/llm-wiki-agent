#!/usr/bin/env python3
"""
Query the LLM Wiki.

Usage:
    python tools/query.py "What are the main themes across all sources?"
    python tools/query.py --project my-project "What are the main themes?"
    python tools/query.py "How does ConceptA relate to ConceptB?" --save
    python tools/query.py "Summarize everything about EntityName" --save synthesis/my-analysis.md

Flags:
    --project <name>    Query a specific project (DB mode)
    --save              Save the answer back into the wiki (prompts for filename)
    --save <path>       Save to a specific wiki path
"""

import sys
import re
import json
import argparse
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools._utils import (
    REPO_ROOT, WIKI_DIR, INDEX_FILE, LOG_FILE, SCHEMA_FILE,
    read_file, write_file, call_llm, append_log,
    file_exists, is_db_mode, use_storage, page_id,
)


def find_relevant_pages(question: str, index_content: str) -> list[Path]:
    md_links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', index_content)
    question_lower = question.lower()
    relevant = []

    for title, href in md_links:
        title_lower = title.lower()
        has_cjk = any('\u4e00' <= ch <= '\u9fff' for ch in title)
        if has_cjk:
            matched = any(
                title_lower[j:j+2] in question_lower
                for j in range(len(title_lower) - 1)
                if any('\u4e00' <= c <= '\u9fff' for c in title_lower[j:j+2])
            )
        else:
            matched = any(word in question_lower for word in title_lower.split() if len(word) > 2)

        if matched:
            p = WIKI_DIR / href
            if file_exists(p) and p not in relevant:
                relevant.append(p)

    graph_json = REPO_ROOT / "graph" / "graph.json"
    if file_exists(graph_json) and relevant:
        try:
            graph_data = json.loads(read_file(graph_json))
            page_ids = set()
            for p in relevant:
                pid = page_id(p)
                page_ids.add(pid)
            neighbors = set()
            for edge in graph_data.get('edges', []):
                if edge.get('confidence', 0) >= 0.7:
                    if edge['from'] in page_ids:
                        neighbors.add(edge['to'])
                    elif edge['to'] in page_ids:
                        neighbors.add(edge['from'])
            for nid in neighbors:
                np = WIKI_DIR / f"{nid}.md"
                if file_exists(np) and np not in relevant:
                    relevant.append(np)
        except (json.JSONDecodeError, KeyError):
            pass

    overview = WIKI_DIR / "overview.md"
    if file_exists(overview) and overview not in relevant:
        relevant.insert(0, overview)
    return relevant[:15]


def query(question: str, save_path: str | None = None):
    today = date.today().isoformat()

    index_content = read_file(INDEX_FILE)
    if not index_content:
        print("Wiki is empty. Ingest some sources first with: python tools/ingest.py <source>")
        sys.exit(1)

    relevant_pages = find_relevant_pages(question, index_content)

    if not relevant_pages or len(relevant_pages) <= 1:
        print("  selecting relevant pages via API...")
        prompt = f"Given this wiki index:\n\n{index_content}\n\nWhich pages are most relevant to answering: \"{question}\"\n\nReturn ONLY a JSON array of relative file paths (as listed in the index), e.g. [\"sources/foo.md\", \"concepts/Bar.md\"]. Maximum 10 pages."
        raw = call_llm(prompt, "LLM_MODEL_FAST", "claude-3-5-haiku-latest", max_tokens=512)
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        try:
            paths = json.loads(raw)
            relevant_pages = [WIKI_DIR / p for p in paths if file_exists(WIKI_DIR / p)]
        except (json.JSONDecodeError, TypeError):
            pass

    pages_context = ""
    for p in relevant_pages:
        rel = page_id(p)
        pages_context += f"\n\n### {rel}\n{read_file(p)}"

    if not pages_context:
        pages_context = f"\n\n### wiki/index.md\n{index_content}"

    schema = read_file(SCHEMA_FILE)

    print(f"  synthesizing answer from {len(relevant_pages)} pages...")
    prompt = f"""You are querying an LLM Wiki to answer a question. Use the wiki pages below to synthesize a thorough answer. Cite sources using [[PageName]] wikilink syntax.

Schema:
{schema}

Wiki pages:
{pages_context}

Question: {question}

Write a well-structured markdown answer with headers, bullets, and [[wikilink]] citations. At the end, add a ## Sources section listing the pages you drew from.
"""
    answer = call_llm(prompt, "LLM_MODEL", "claude-3-5-sonnet-latest", max_tokens=4096)
    print("\n" + "=" * 60)
    print(answer)
    print("=" * 60)

    if save_path is not None:
        if save_path == "":
            slug = input("\nSave as (slug, e.g. 'my-analysis'): ").strip()
            if not slug:
                print("Skipping save.")
                return
            save_path = f"syntheses/{slug}.md"

        full_save_path = WIKI_DIR / save_path
        frontmatter = f"""---
title: "{question[:80]}"
type: synthesis
tags: []
sources: []
last_updated: {today}
---

"""
        write_file(full_save_path, frontmatter + answer)

        index_content = read_file(INDEX_FILE)
        entry = f"- [{question[:60]}]({save_path}) — synthesis"
        if "## Syntheses" in index_content:
            index_content = index_content.replace("## Syntheses\n", f"## Syntheses\n{entry}\n")
        write_file(INDEX_FILE, index_content)
        print(f"  indexed: {save_path}")

    append_log(f"## [{today}] query | {question[:80]}\n\nSynthesized answer from {len(relevant_pages)} pages." +
               (f" Saved to {save_path}." if save_path else ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query the LLM Wiki")
    parser.add_argument("question", help="Question to ask the wiki")
    parser.add_argument("--project", type=str, default=None, help="Project name (DB mode)")
    parser.add_argument("--save", nargs="?", const="", default=None,
                        help="Save answer to wiki (optionally specify path)")
    args = parser.parse_args()

    if args.project:
        from storage.db import WikiStorage
        db = WikiStorage("storage/wiki.db")
        proj = db.get_project_by_name(args.project)
        if not proj:
            print(f"Error: project '{args.project}' not found.")
            sys.exit(1)
        use_storage(db, proj["id"])
        print(f"[DB mode] Using project: {args.project} (id={proj['id']})")

    query(args.question, args.save)
