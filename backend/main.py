"""
Phase 1 backend — read-only search/browse API over the catalog produced
by the pipeline. No auth, no writes: this is the MVP surface described
in the phase plan (search + browse + download only).

Run locally:
    uvicorn main:app --reload --port 8000

DB: reads the same SQLite file the pipeline writes to. For cloud deployment,
swap get_connection() for a Postgres connection (see DEPLOY.md) — the SQL
in this file is plain enough to port with minimal changes.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline"))
from db import get_connection as _init_db_connection  # noqa: E402
from admin_routes import router as admin_router  # noqa: E402
from rate_limit import limiter  # noqa: E402

DB_PATH = Path(__file__).parent.parent / "data" / "catalog" / "catalog.db"

app = FastAPI(title="Resource Catalog API", version="0.1.0")

# Rate limiting — shared limiter instance imported by admin_routes.py so
# /auth/login and /auth/register can be limited per-IP. Complements the
# per-account lockout in auth.py: this stops one IP hammering many accounts,
# lockout stops many IPs hammering one account.
app.state.limiter = limiter


async def _rate_limit_handler(request, exc: Exception):
    # slowapi's own handler is typed for (Request, RateLimitExceeded), which
    # doesn't structurally match Starlette's generic ExceptionHandler type —
    # this thin wrapper exists only to satisfy strict type checking; the
    # isinstance check is always true in practice since we only register this
    # for RateLimitExceeded below.
    assert isinstance(exc, RateLimitExceeded)
    return _rate_limit_exceeded_handler(request, exc)


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# Ensures all tables (including admin/jobs, added for Phase 2) exist even on a
# fresh clone — get_connection() runs the full schema idempotently.
_init_db_connection(str(DB_PATH)).close()

app.include_router(admin_router)

# CORS: ALLOWED_ORIGINS env var is a comma-separated list of real frontend
# origins (e.g. "https://examvault.example.com"). Defaults to common local
# dev ports only — never wildcard-open by default, since "*" here means any
# website can call this API from a browser holding a valid token.
_default_dev_origins = "http://localhost:5173,http://127.0.0.1:5173"
allowed_origins = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", _default_dev_origins).split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class CatalogEntry(BaseModel):
    id: int
    filename: str
    subject: Optional[str]
    level: Optional[str]
    year: Optional[int]
    session: Optional[str]
    syllabus_era: Optional[str]
    paper_number: Optional[int]
    doc_type: Optional[str]
    exam_board: Optional[str]
    confidence: Optional[str]
    needs_review: bool = False


class SearchResponse(BaseModel):
    total: int
    results: list[CatalogEntry]


class FacetsResponse(BaseModel):
    subjects: list[str]
    levels: list[str]
    years: list[int]
    exam_boards: list[str]
    sessions: list[str]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/facets", response_model=FacetsResponse)
def facets():
    """Distinct values for building filter dropdowns in the UI."""
    conn = get_db()
    try:
        def col(name: str, order_desc: bool = False):
            order = "DESC" if order_desc else "ASC"
            rows = conn.execute(
                f"SELECT DISTINCT {name} FROM catalog WHERE {name} IS NOT NULL ORDER BY {name} {order}"
            ).fetchall()
            return [r[0] for r in rows]

        return FacetsResponse(
            subjects=col("subject"),
            levels=col("level"),
            years=col("year", order_desc=True),
            exam_boards=col("exam_board"),
            sessions=["June", "November"],
        )
    finally:
        conn.close()


@app.get("/search", response_model=SearchResponse)
def search(
    q: Optional[str] = Query(None, description="free-text match against filename/snippet"),
    subject: Optional[str] = None,
    level: Optional[str] = None,
    year: Optional[int] = None,
    exam_board: Optional[str] = None,
    session: Optional[str] = Query(None, pattern="^(June|November)$"),
    syllabus_era: Optional[str] = None,
    exclude_needs_review: bool = True,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    conn = get_db()
    try:
        clauses = []
        params: list = []

        if q:
            clauses.append("(filename LIKE ? OR text_snippet LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%"])
        if subject:
            clauses.append("subject = ?")
            params.append(subject)
        if level:
            clauses.append("level = ?")
            params.append(level)
        if year:
            clauses.append("year = ?")
            params.append(year)
        if exam_board:
            clauses.append("exam_board = ?")
            params.append(exam_board)
        if session:
            clauses.append("session = ?")
            params.append(session)
        if syllabus_era:
            clauses.append("syllabus_era = ?")
            params.append(syllabus_era)
        if exclude_needs_review:
            clauses.append("needs_review = 0")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        total = conn.execute(f"SELECT COUNT(*) FROM catalog {where}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT id, filename, subject, level, year, session, syllabus_era, paper_number,
                       doc_type, exam_board, confidence, needs_review
                FROM catalog {where}
                ORDER BY year DESC, subject, paper_number
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()

        return SearchResponse(total=total, results=[CatalogEntry(**dict(r)) for r in rows])
    finally:
        conn.close()


@app.get("/papers/latest", response_model=list[CatalogEntry])
def latest_papers(limit: int = Query(10, le=50)):
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, filename, subject, level, year, session, syllabus_era, paper_number,
                      doc_type, exam_board, confidence
               FROM catalog WHERE needs_review = 0
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [CatalogEntry(**dict(r)) for r in rows]
    finally:
        conn.close()


@app.get("/papers/popular", response_model=list[CatalogEntry])
def popular_papers(limit: int = Query(10, le=50)):
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, filename, subject, level, year, session, syllabus_era, paper_number,
                      doc_type, exam_board, confidence
               FROM catalog WHERE needs_review = 0
               ORDER BY COALESCE(download_count, 0) DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [CatalogEntry(**dict(r)) for r in rows]
    finally:
        conn.close()


@app.get("/papers/{paper_id}")
def get_paper(paper_id: int):
    conn = get_db()
    try:
        row = conn.execute(
            """SELECT id, filename, subject, level, year, session, syllabus_era,
                      paper_number, doc_type, exam_board, confidence
               FROM catalog WHERE id = ? AND needs_review = 0""",
            (paper_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Not found")
        return dict(row)
    finally:
        conn.close()


@app.get("/papers/{paper_id}/download")
def download_paper(paper_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT path, filename FROM catalog WHERE id = ?", (paper_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Not found")
        path = Path(row["path"]).resolve()
        upload_root = (Path(__file__).parent.parent / "data" / "intake" / "uploads").resolve()
        if upload_root not in path.parents or not path.is_file():
            raise HTTPException(404, "File missing on disk")
        conn.execute(
            "UPDATE catalog SET download_count = COALESCE(download_count, 0) + 1 WHERE id = ?",
            (paper_id,),
        )
        conn.commit()
        return FileResponse(path, filename=row["filename"], media_type={".pdf":"application/pdf", ".docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".png":"image/png", ".jpg":"image/jpeg", ".jpeg":"image/jpeg"}.get(path.suffix.lower(), "application/octet-stream"))
    finally:
        conn.close()


class SubjectSummary(BaseModel):
    subject: str
    count: int


@app.get("/subjects", response_model=list[SubjectSummary])
def subjects():
    """Powers the 'Browse by Subject' cards on the home screen."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT subject, COUNT(*) as count FROM catalog "
            "WHERE subject IS NOT NULL AND needs_review = 0 "
            "GROUP BY subject ORDER BY count DESC"
        ).fetchall()
        return [SubjectSummary(subject=r["subject"], count=r["count"]) for r in rows]
    finally:
        conn.close()



