#!/usr/bin/env python3
"""
LLM Wiki Compiler Service — REST API

Provides APIs for:
  - Project management (create, list, get, delete)
  - File sync (upload files → convert to .md → store in raw/)
  - Wiki compilation (ingest + build graph)
  - Wiki lint/health check
  - Wiki query
  - Project export (raw/, wiki/, graph/ as zip)

Usage:
    python server.py
    python server.py --host 0.0.0.0 --port 8000
    uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import zipfile
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))

from storage.db import WikiStorage
from tools._utils import use_storage

DB_PATH = REPO_ROOT / "storage" / "wiki.db"
CONVERTIBLE_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls",
    ".html", ".htm", ".txt", ".csv", ".json", ".xml",
    ".rst", ".rtf", ".epub", ".ipynb",
    ".yaml", ".yml", ".tsv",
    ".wav", ".mp3",
}

app = FastAPI(
    title="LLM Wiki Compiler",
    description="Multi-project wiki knowledge compiler engine",
    version="2.0.0",
)


class ProjectInfo(BaseModel):
    name: str
    description: str = ""


class QueryRequest(BaseModel):
    question: str
    save: bool = False


class CompileOptions(BaseModel):
    no_infer: bool = False
    clean: bool = False


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Any = None


def _get_db() -> WikiStorage:
    return WikiStorage(str(DB_PATH))


def _activate_project(db: WikiStorage, project_name: str) -> dict:
    proj = db.get_project_by_name(project_name)
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
    use_storage(db, proj["id"])
    return proj


@contextmanager
def _capture_stdout():
    buf = io.StringIO()
    with redirect_stdout(buf):
        yield buf


# ═══════════════════════════════════════════════════════════════════
# Project Management
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/projects", response_model=ApiResponse)
def create_project(info: ProjectInfo):
    db = _get_db()
    try:
        existing = db.get_project_by_name(info.name)
        if existing:
            raise HTTPException(status_code=409, detail=f"Project '{info.name}' already exists")
        pid = db.create_project(info.name, info.description)
        return ApiResponse(success=True, message="Project created", data={"id": pid, "name": info.name})
    finally:
        db.close()


@app.get("/api/projects", response_model=ApiResponse)
def list_projects():
    db = _get_db()
    try:
        projects = db.list_projects()
        return ApiResponse(success=True, message=f"{len(projects)} project(s)", data=projects)
    finally:
        db.close()


@app.get("/api/projects/{name}", response_model=ApiResponse)
def get_project(name: str):
    db = _get_db()
    try:
        proj = db.get_project_by_name(name)
        if not proj:
            raise HTTPException(status_code=404, detail=f"Project '{name}' not found")
        stats = db.project_stats(proj["id"])
        return ApiResponse(success=True, message="OK", data=stats)
    finally:
        db.close()


@app.delete("/api/projects/{name}", response_model=ApiResponse)
def delete_project(name: str):
    db = _get_db()
    try:
        proj = db.get_project_by_name(name)
        if not proj:
            raise HTTPException(status_code=404, detail=f"Project '{name}' not found")
        db.delete_project(proj["id"])
        return ApiResponse(success=True, message=f"Project '{name}' deleted")
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════
# File Sync
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/projects/{name}/sync", response_model=ApiResponse)
async def sync_files(name: str, files: list[UploadFile] = File(...)):
    db = _get_db()
    try:
        proj = _activate_project(db, name)
        pid = proj["id"]

        imported = []
        skipped = []
        failed = []

        for f in files:
            if not f.filename:
                continue

            filename = f.filename.replace("\\", "/")
            rel_path = f"raw/{filename}"

            existing = db.get_file_by_path(pid, rel_path)

            content_bytes = await f.read()
            if not content_bytes:
                continue

            suffix = Path(filename).suffix.lower()

            if suffix == ".md":
                content = content_bytes.decode("utf-8")
                if existing:
                    skipped.append(filename)
                    continue
            elif suffix in CONVERTIBLE_EXTENSIONS:
                try:
                    from markitdown import MarkItDown
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                        tmp.write(content_bytes)
                        tmp_path = tmp.name
                    try:
                        md = MarkItDown(enable_plugins=False)
                        result = md.convert(tmp_path)
                        content = result.text_content
                    finally:
                        Path(tmp_path).unlink(missing_ok=True)
                except Exception as e:
                    failed.append({"filename": filename, "error": str(e)})
                    continue

                md_rel_path = f"raw/{Path(filename).with_suffix('.md').as_posix()}"
                if db.get_file_by_path(pid, md_rel_path):
                    skipped.append(filename)
                    continue
                rel_path = md_rel_path
            else:
                failed.append({"filename": filename, "error": f"Unsupported format: {suffix}"})
                continue

            db.add_file(pid, rel_path, content)
            imported.append(filename)

        return ApiResponse(
            success=True,
            message=f"Imported: {len(imported)}, Skipped: {len(skipped)}, Failed: {len(failed)}",
            data={"imported": imported, "skipped": skipped, "failed": failed},
        )
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════
# Wiki Compilation (Ingest + Build Graph)
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/projects/{name}/ingest", response_model=ApiResponse)
def ingest_project(name: str):
    db = _get_db()
    try:
        proj = _activate_project(db, name)
        pid = proj["id"]

        raw_files = db.list_files(pid, prefix="raw/")
        md_files = [f for f in raw_files if f["file_name"].endswith(".md")]
        if not md_files:
            return ApiResponse(success=True, message="No raw/*.md files to ingest", data={"ingested": 0})

        from tools.ingest import ingest as ingest_one

        safety = sys.exit
        results = []
        for f in md_files:
            path = str(REPO_ROOT / f["relative_path"])
            try:
                sys.exit = lambda code=0: (_ for _ in ()).throw(ValueError(f"Ingest aborted: {code}"))
                with _capture_stdout() as buf:
                    ingest_one(path, auto_convert=False)
                results.append({"file": f["relative_path"], "status": "ok", "output": buf.getvalue()[-500:]})
            except ValueError:
                results.append({"file": f["relative_path"], "status": "error", "error": "Ingest aborted"})
            except Exception as e:
                results.append({"file": f["relative_path"], "status": "error", "error": str(e)})
            finally:
                sys.exit = safety

        ok = sum(1 for r in results if r["status"] == "ok")
        return ApiResponse(
            success=True,
            message=f"Ingested {ok}/{len(md_files)} files",
            data={"total": len(md_files), "ingested": ok, "details": results},
        )
    finally:
        db.close()


@app.post("/api/projects/{name}/build-graph", response_model=ApiResponse)
def build_graph_project(name: str, options: CompileOptions = CompileOptions()):
    db = _get_db()
    try:
        proj = _activate_project(db, name)

        from tools.build_graph import build_graph

        with _capture_stdout() as buf:
            build_graph(infer=not options.no_infer, open_browser=False, clean=options.clean)

        return ApiResponse(success=True, message="Graph built", data={"output": buf.getvalue()[-1000:]})
    finally:
        db.close()


@app.post("/api/projects/{name}/compile", response_model=ApiResponse)
def compile_project(name: str, options: CompileOptions = CompileOptions()):
    ingest_resp = ingest_project(name)
    if not ingest_resp.success:
        return ingest_resp

    graph_resp = build_graph_project(name, options)

    return ApiResponse(
        success=True,
        message=f"Compilation complete. Ingest: {ingest_resp.message}. Graph: {graph_resp.message}",
        data={"ingest": ingest_resp.data, "graph": graph_resp.data},
    )


# ═══════════════════════════════════════════════════════════════════
# Lint & Health
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/projects/{name}/lint", response_model=ApiResponse)
def lint_project(name: str):
    db = _get_db()
    try:
        proj = _activate_project(db, name)

        from tools.lint import run_lint
        from tools._utils import WIKI_DIR

        report = run_lint()
        report_path = WIKI_DIR / "lint-report.md"
        from tools._utils import write_file
        write_file(report_path, report)

        return ApiResponse(
            success=True,
            message="Lint complete",
            data={"report": report, "path": "wiki/lint-report.md"},
        )
    finally:
        db.close()


@app.post("/api/projects/{name}/health", response_model=ApiResponse)
def health_check_project(name: str):
    db = _get_db()
    try:
        proj = _activate_project(db, name)

        from tools.health import run_health
        results = run_health()

        return ApiResponse(success=True, message="Health check complete", data=results)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════
# Query
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/projects/{name}/query", response_model=ApiResponse)
def query_project(name: str, req: QueryRequest):
    db = _get_db()
    try:
        proj = _activate_project(db, name)

        from tools.query import query
        from tools._utils import INDEX_FILE

        index_content = db.get_file_text_by_path(proj["id"], "wiki/index.md")
        if not index_content:
            raise HTTPException(status_code=400, detail="Wiki is empty. Sync and ingest files first.")

        save_path = None
        if req.save:
            slug = req.question[:60].replace(" ", "-").replace("?", "").lower()
            save_path = f"syntheses/{slug}.md"

        with _capture_stdout() as buf:
            query(req.question, save_path)

        return ApiResponse(
            success=True,
            message="Query complete",
            data={"answer": buf.getvalue(), "saved": save_path},
        )
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════════════════════

@app.get("/api/projects/{name}/export")
def export_project(name: str):
    db = _get_db()
    try:
        proj = db.get_project_by_name(name)
        if not proj:
            raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            db.export_project(proj["id"], tmpdir)

            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                base = Path(tmpdir)
                for fpath in base.rglob("*"):
                    if fpath.is_file():
                        arcname = str(fpath.relative_to(base))
                        zf.write(fpath, arcname)
            zip_buf.seek(0)

            return StreamingResponse(
                zip_buf,
                media_type="application/zip",
                headers={"Content-Disposition": f"attachment; filename={name}-wiki-export.zip"},
            )
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)