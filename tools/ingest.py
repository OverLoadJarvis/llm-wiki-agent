#!/usr/bin/env python3
"""
Ingest a source document into the LLM Wiki.

Usage:
    python tools/ingest.py <path-to-source>
    python tools/ingest.py raw/articles/my-article.md
    python tools/ingest.py report.pdf                  # auto-converts to .md
    python tools/ingest.py slides.pptx notes.docx       # batch, mixed formats
    python tools/ingest.py raw/mixed/ --no-convert      # skip auto-conversion
    python tools/ingest.py --validate-only              # run validation only

Supported formats (auto-converted via markitdown):
    .pdf .docx .pptx .xlsx .html .htm .txt .csv .json .xml
    .rst .rtf .epub .ipynb .yaml .yml .tsv .wav .mp3

The LLM reads the source, extracts knowledge, and updates the wiki:
  - Creates wiki/sources/<slug>.md
  - Updates wiki/index.md
  - Updates wiki/overview.md (if warranted)
  - Creates/updates entity and concept pages
  - Appends to wiki/log.md
  - Flags contradictions
  - Runs post-ingest validation (broken links, index coverage)
"""

import sys
import json
import re
import tempfile
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools._utils import (
    REPO_ROOT, WIKI_DIR, RAW_DIR, LOG_FILE, INDEX_FILE, OVERVIEW_FILE, SCHEMA_FILE,
    read_file, write_file, call_llm, sha256,
    extract_wikilinks, append_log, page_stem_set, all_wiki_pages, page_id,
    file_exists, file_mtime, list_dir, is_db_mode, use_storage,
)

# File extensions that can be auto-converted to markdown via markitdown.
# .md files are ingested directly without conversion.
CONVERTIBLE_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls",
    ".html", ".htm", ".txt", ".csv", ".json", ".xml",
    ".rst", ".rtf", ".epub", ".ipynb",
    ".yaml", ".yml", ".tsv",
    ".wav", ".mp3",  # audio transcription via markitdown
}
ALL_SUPPORTED_EXTENSIONS = {".md"} | CONVERTIBLE_EXTENSIONS   # | 集合运算符，并集


def build_wiki_context() -> str:
    parts = []
    if file_exists(INDEX_FILE):
        parts.append(f"## wiki/index.md\n{read_file(INDEX_FILE)}")
    if file_exists(OVERVIEW_FILE):
        parts.append(f"## wiki/overview.md\n{read_file(OVERVIEW_FILE)}")
    sources_dir = WIKI_DIR / "sources"
    recent = list_dir(sources_dir, "*.md")
    recent.sort(key=lambda p: file_mtime(p) if is_db_mode() else p.stat().st_mtime, reverse=True)
    for p in recent[:5]:
        rel_path = p.as_posix()
        if not is_db_mode():
            rel_path = str(p.relative_to(REPO_ROOT))
        parts.append(f"## {rel_path}\n{read_file(p)}")
    return "\n\n---\n\n".join(parts)


def parse_json_from_response(text: str) -> dict:
    """
    从模型回复中解析JSON对象，返回字典
    """
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())

    # Find the outermost JSON object
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in response")
    return json.loads(match.group())


def update_index(new_entry: str, section: str = "Sources"):
    """
    更新Wiki索引，添加新条目
    """
    content = read_file(INDEX_FILE)
    if not content:
        content = "# Wiki Index\n\n## Overview\n- [Overview](overview.md) — living synthesis\n\n## Sources\n\n## Entities\n\n## Concepts\n\n## Syntheses\n"
    section_header = f"## {section}"
    if section_header in content:
        content = content.replace(section_header + "\n", section_header + "\n" + new_entry + "\n")
    else:
        content += f"\n{section_header}\n{new_entry}\n"
    write_file(INDEX_FILE, content)


def validate_ingest(changed_pages: list[str] | None = None) -> dict:
    existing_pages = page_stem_set()
    index_content = read_file(INDEX_FILE).lower()

    if changed_pages:
        scan_paths = [WIKI_DIR / p for p in changed_pages if file_exists(WIKI_DIR / p)]
    else:
        scan_paths = [p for p in all_wiki_pages()]

    broken_links = []
    for page_path in scan_paths:
        content = read_file(page_path)
        rel = page_id(page_path)
        for link in extract_wikilinks(content):
            link_stem = Path(link).stem.lower() if '/' in link else link.lower()
            if link_stem not in existing_pages:
                broken_links.append((rel, link))

    unindexed = []
    for p in (changed_pages or []):
        page_path = WIKI_DIR / p
        if file_exists(page_path):
            stem = page_path.stem.lower()
            if stem not in index_content and p not in ("log.md", "overview.md"):
                unindexed.append(p)

    return {"broken_links": broken_links, "unindexed": unindexed}


def _to_db_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def convert_to_md(source: Path) -> Path:
    """Convert a non-markdown file to .md using markitdown.

    Returns the path to the converted .md file (placed next to the original
    with a .md extension, or in a temp location if the source dir is read-only).
    将非Markdown文件转换为Markdown文件，返回转换后的文件路径。
    如果源目录只读，将转换后的文件放在临时目录中。
    """
    try:
        from markitdown import MarkItDown
    except ImportError:
        print("Error: markitdown not installed (needed to convert non-.md files).")
        print("  Install with: pip install markitdown")
        sys.exit(1)

    md = MarkItDown(enable_plugins=False)
    try:
        result = md.convert(str(source))
    except Exception as e:
        print(f"Error: failed to convert '{source.name}': {e}")
        sys.exit(1)

    # Write converted output next to source as <name>.md
    output = source.with_suffix(".md")
    try:
        output.write_text(result.text_content, encoding="utf-8")
    except OSError:
        # Fallback: source directory may be read-only
        tmp = Path(tempfile.mkdtemp()) / f"{source.stem}.md"
        tmp.write_text(result.text_content, encoding="utf-8")
        output = tmp

    print(f"  ✓ Converted {source.name} → {output.name}")
    return output


def ingest(source_path: str, auto_convert: bool = True):
    source = Path(source_path)
    if not file_exists(source):
        print(f"Error: file not found: {source_path}")
        sys.exit(1)

    converted_path = None
    if source.suffix.lower() != ".md":
        if is_db_mode():
            print(f"  ❌  DB mode only supports .md files (raw files should be pre-converted).")
            print(f"       Use: python tools/file_to_md.py --project <name> --input_dir <dir>")
            return
        if not auto_convert:
            print(f"  Skipping non-.md file (--no-convert): {source.name}")
            return
        if source.suffix.lower() not in CONVERTIBLE_EXTENSIONS:
            print(f"  ⚠️  Unsupported format: {source.suffix} — skipping {source.name}")
            print(f"       Supported: {', '.join(sorted(ALL_SUPPORTED_EXTENSIONS))}")
            return
        print(f"  Converting {source.name} to markdown...")
        converted_path = convert_to_md(source)
        source = converted_path
        source_content = source.read_text(encoding="utf-8")
    else:
        source_content = read_file(source)

    source_hash = sha256(source_content)
    today = date.today().isoformat()

    print(f"\nIngesting: {source.name}  (hash: {source_hash})")

    wiki_context = build_wiki_context()

    schema = read_file(SCHEMA_FILE)

    source_label = _to_db_path(source) if is_db_mode() else (
        str(source.relative_to(REPO_ROOT)) if source.is_relative_to(REPO_ROOT) else source.name
    )

    prompt = f"""You are maintaining an LLM Wiki. Process this source document and integrate its knowledge into the wiki.

Schema and conventions:
{schema}

Current wiki state (index + recent pages):
{wiki_context if wiki_context else "(wiki is empty — this is the first source)"}

New source to ingest (file: {source_label}):
=== SOURCE START ===
{source_content}
=== SOURCE END ===

Today's date: {today}

Return ONLY a valid JSON object with these fields (no markdown fences, no prose outside the JSON):
{{
  "title": "Human-readable title for this source",
  "slug": "kebab-case-slug-for-filename",
  "source_page": "full markdown content for wiki/sources/<slug>.md — use the source page format from the schema. CRITICAL: Aggressively convert key people, products, concepts and projects into [[Wikilinks]] inline in the text. Omitting [[ ]] for known terms is a failure.",
  "index_entry": "- [Title](sources/slug.md) — one-line summary",
  "overview_update": "full updated content for wiki/overview.md, or null if no update needed",
  "entity_pages": [
    {{"path": "entities/EntityName.md", "content": "full markdown content"}}
  ],
  "concept_pages": [
    {{"path": "concepts/ConceptName.md", "content": "full markdown content"}}
  ],
  "contradictions": ["describe any contradiction with existing wiki content, or empty list"],
  "log_entry": "## [{today}] ingest | <title>\\n\\nAdded source. Key claims: ..."
}}
"""

    print(f"  calling API (model: ...)")
    raw = call_llm(prompt, max_tokens=8192)
    try:
        data = parse_json_from_response(raw)
    except (ValueError, json.JSONDecodeError) as e:
        # 解析失败，没有返回JSON格式的内容
        print(f"Error parsing API response: {e}")
        print("Raw response saved to /tmp/ingest_debug.txt")
        Path("/tmp/ingest_debug.txt").write_text(raw)
        sys.exit(1)

    # Write source page
    slug = data["slug"]
    write_file(WIKI_DIR / "sources" / f"{slug}.md", data["source_page"])

    # Write entity pages
    for page in data.get("entity_pages", []):
        write_file(WIKI_DIR / page["path"], page["content"])

    # Write concept pages 
    for page in data.get("concept_pages", []):
        write_file(WIKI_DIR / page["path"], page["content"])

    # Update overview 直接就是大模型来更新overview.md文件
    if data.get("overview_update"):
        write_file(OVERVIEW_FILE, data["overview_update"])

    # Update index
    update_index(data["index_entry"], section="Sources")

    # Append log
    append_log(data["log_entry"])

    # Report contradictions 如果有矛盾，打印出来，也是大模型直接判断是否有冲突
    contradictions = data.get("contradictions", [])
    if contradictions:
        print("\n  ⚠️  Contradictions detected:")
        for c in contradictions:
            print(f"     - {c}")

    # --- Post-ingest validation ---
    created_pages = [f"sources/{slug}.md"]
    for page in data.get("entity_pages", []):
        created_pages.append(page["path"])
    for page in data.get("concept_pages", []):
        created_pages.append(page["path"])
    updated_pages = ["index.md", "log.md"]
    if data.get("overview_update"):
        updated_pages.append("overview.md")

    validation = validate_ingest(created_pages)

    print(f"\n{'='*50}")
    print(f"  ✅ Ingested: {data['title']}")
    print(f"{'='*50}")
    print(f"  Created : {len(created_pages)} pages")
    for p in created_pages:
        print(f"           + wiki/{p}")
    print(f"  Updated : {len(updated_pages)} pages")
    for p in updated_pages:
        print(f"           ~ wiki/{p}")
    if contradictions:
        print(f"  Warnings: {len(contradictions)} contradiction(s)")
    if validation["broken_links"]:
        print(f"  ⚠️  Broken links: {len(validation['broken_links'])}")
        for page, link in validation["broken_links"][:10]:
            print(f"           wiki/{page} → [[{link}]]")
        if len(validation["broken_links"]) > 10:
            print(f"           ... and {len(validation['broken_links']) - 10} more")
    if validation["unindexed"]:
        print(f"  ⚠️  Not in index.md: {len(validation['unindexed'])}")
        for p in validation["unindexed"][:10]:
            print(f"           wiki/{p}")
        if len(validation["unindexed"]) > 10:
            print(f"           ... and {len(validation['unindexed']) - 10} more")
    if not validation["broken_links"] and not validation["unindexed"]:
        print("  ✓ Validation passed — no broken links, all pages indexed")
    print()


if __name__ == "__main__":
    # Parse --project for DB mode
    project_name = None
    remaining_args = []
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--project" and i + 1 < len(sys.argv):
            project_name = sys.argv[i + 1]
            i += 2
        else:
            remaining_args.append(sys.argv[i])
            i += 1

    if project_name:
        from storage.db import WikiStorage
        db = WikiStorage("storage/wiki.db")
        proj = db.get_project_by_name(project_name)
        if not proj:
            print(f"Error: project '{project_name}' not found. Create it first with storage API.")
            sys.exit(1)
        use_storage(db, proj["id"])
        print(f"[DB mode] Using project: {project_name} (id={proj['id']})")

    # Handle --validate-only flag
    if len(remaining_args) == 1 and remaining_args[0] == "--validate-only":
        print("Running wiki validation (no ingest)...\n")
        result = validate_ingest()
        if result["broken_links"]:
            print(f"Broken wikilinks: {len(result['broken_links'])}")
            for page, link in result["broken_links"][:20]:
                print(f"  wiki/{page} → [[{link}]]")
            if len(result["broken_links"]) > 20:
                print(f"  ... and {len(result['broken_links']) - 20} more")
        else:
            print("No broken wikilinks found.")
        print()
        pages = page_stem_set()
        index_content = read_file(INDEX_FILE).lower()
        unindexed_all = []
        for p in all_wiki_pages():
            stem = p.stem.lower()
            if stem not in index_content:
                unindexed_all.append(page_id(p))
        if unindexed_all:
            print(f"Pages not in index.md: {len(unindexed_all)}")
            for up in unindexed_all[:20]:
                print(f"  wiki/{up}")
            if len(unindexed_all) > 20:
                print(f"  ... and {len(unindexed_all) - 20} more")
        else:
            print("All pages are indexed.")
        sys.exit(0)

    # Parse flags
    no_convert = "--no-convert" in remaining_args
    args = [a for a in remaining_args if not a.startswith("--")]

    if not args:
        print("Usage: python tools/ingest.py [--project <name>] <path-to-source> [path2 ...] [dir1 ...]")
        print("       python tools/ingest.py [--project <name>] --validate-only")
        print("       python tools/ingest.py --no-convert  # skip auto-conversion of non-.md files")
        print(f"\nSupported formats: {', '.join(sorted(ALL_SUPPORTED_EXTENSIONS))}")
        sys.exit(1)

    paths_to_process = []
    for arg in args:
        p = Path(arg)
        if is_db_mode():
            # In DB mode, paths are relative to project and must be looked up in DB
            p = REPO_ROOT / arg
            if file_exists(p):
                paths_to_process.append(p)
            else:
                print(f"  ⚠️  File not found in project: {arg}")
        elif p.is_file():
            ext = p.suffix.lower()
            if ext in ALL_SUPPORTED_EXTENSIONS:
                paths_to_process.append(p)
            else:
                print(f"  ⚠️  Skipping unsupported format: {p.name} ({ext})")
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and f.suffix.lower() in ALL_SUPPORTED_EXTENSIONS:
                    paths_to_process.append(f)
        else:
            import glob
            for f in glob.glob(arg, recursive=True):
                g_p = Path(f)
                if g_p.is_file() and g_p.suffix.lower() in ALL_SUPPORTED_EXTENSIONS:
                    paths_to_process.append(g_p)

    # Deduplicate while preserving order
    unique_paths = []
    seen = set()
    for p in paths_to_process:
        abs_p = p.resolve() if not is_db_mode() else p
        key = str(abs_p)
        if key not in seen:
            seen.add(key)
            unique_paths.append(p)

    if not unique_paths:
        print("Error: no supported files found to ingest.")
        print(f"Supported formats: {', '.join(sorted(ALL_SUPPORTED_EXTENSIONS))}")
        sys.exit(1)

    if len(unique_paths) > 1:
        print(f"Batch mode: found {len(unique_paths)} files to ingest.")

    for p in unique_paths:
        ingest(str(p), auto_convert=not no_convert)
