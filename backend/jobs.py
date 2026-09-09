"""
Background job processing for bulk import, with live per-file status pushed
over WebSocket. Runs the (blocking, CPU/IO-heavy) pipeline stages in a thread
pool so the FastAPI event loop stays responsive, and broadcasts progress after
each file completes.

This is genuinely async and non-blocking, but intentionally in-process rather
than Redis/RQ/Celery-backed — fine for a single backend instance. See
README.md's "scaling the job queue" note for the upgrade path once import
volume or multi-instance deployment calls for it.
"""
from __future__ import annotations

import asyncio
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline"))

from intake import walk_and_hash  # noqa: E402
from run_pipeline import process_one_file  # noqa: E402
from db import get_connection, upsert_record  # noqa: E402

EXECUTOR = ThreadPoolExecutor(max_workers=4)
MAX_CONCURRENT_FILES = 4

# Batch IDs the admin has cancelled. Checked cooperatively between files —
# see the note in _process_batch about why we can't interrupt an in-flight
# OCR call mid-execution.
_cancelled_batches: set[int] = set()


def request_cancel(batch_id: int) -> None:
    _cancelled_batches.add(batch_id)


def _is_cancelled(batch_id: int) -> bool:
    return batch_id in _cancelled_batches


class ConnectionManager:
    def __init__(self):
        self._connections: dict[int, list] = {}

    async def connect(self, batch_id: int, websocket):
        await websocket.accept()
        self._connections.setdefault(batch_id, []).append(websocket)

    def disconnect(self, batch_id: int, websocket):
        conns = self._connections.get(batch_id, [])
        if websocket in conns:
            conns.remove(websocket)

    async def broadcast(self, batch_id: int, message: dict):
        for ws in list(self._connections.get(batch_id, [])):
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                self.disconnect(batch_id, ws)


manager = ConnectionManager()


def _db_execute(db_path: str, fn, *args, **kwargs):
    conn = get_connection(db_path)
    try:
        return fn(conn, *args, **kwargs)
    finally:
        conn.close()


def _create_batch_row(conn, source_folder: str, created_by: int, total: int) -> int:
    cur = conn.execute(
        "INSERT INTO import_batches (source_folder, created_by, status, total_files) "
        "VALUES (?, ?, 'running', ?)",
        (source_folder, created_by, total),
    )
    conn.commit()
    return cur.lastrowid


def _create_job_rows(conn, batch_id: int, records):
    for rec in records:
        conn.execute(
            "INSERT INTO import_jobs (batch_id, filename, path, status) VALUES (?, ?, ?, 'queued')",
            (batch_id, rec.filename, rec.path),
        )
    conn.commit()
    rows = conn.execute(
        "SELECT id, filename, path FROM import_jobs WHERE batch_id = ? ORDER BY id", (batch_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def _update_job(conn, job_id: int, **fields):
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE import_jobs SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (*fields.values(), job_id),
    )
    conn.commit()


def _bump_batch_counts(conn, batch_id: int, **increments):
    sets = ", ".join(f"{k} = {k} + ?" for k in increments)
    conn.execute(
        f"UPDATE import_batches SET {sets} WHERE id = ?", (*increments.values(), batch_id)
    )
    conn.commit()


def _finish_batch(conn, batch_id: int):
    conn.execute(
        "UPDATE import_batches SET status = 'done', finished_at = CURRENT_TIMESTAMP WHERE id = ?",
        (batch_id,),
    )
    conn.commit()


def _cancel_batch_row(conn, batch_id: int):
    conn.execute(
        "UPDATE import_batches SET status = 'cancelled', finished_at = CURRENT_TIMESTAMP WHERE id = ?",
        (batch_id,),
    )
    conn.execute(
        "UPDATE import_jobs SET status = 'cancelled' WHERE batch_id = ? AND status IN ('queued', 'extracting')",
        (batch_id,),
    )
    conn.commit()


async def start_batch(db_path: str, source_folder: str, created_by: int, use_tier2: bool = True) -> int:
    """
    Kicks off a bulk import: hashes the folder, creates batch + job rows, then
    launches the async processing task. Returns the new batch_id immediately
    so the caller can open a WebSocket to watch progress.
    """
    loop = asyncio.get_event_loop()
    records = await loop.run_in_executor(EXECUTOR, walk_and_hash, source_folder)

    batch_id = _db_execute(db_path, _create_batch_row, source_folder, created_by, len(records))
    jobs = _db_execute(db_path, _create_job_rows, batch_id, records)

    asyncio.create_task(_process_batch(db_path, batch_id, records, jobs, use_tier2))
    return batch_id


async def _process_batch(db_path, batch_id, records, jobs, use_tier2):
    loop = asyncio.get_event_loop()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_FILES)
    job_by_path = {j["path"]: j["id"] for j in jobs}

    await manager.broadcast(batch_id, {
        "type": "batch_started", "batch_id": batch_id, "total_files": len(records),
    })

    async def handle_one(rec):
        job_id = job_by_path[rec.path]
        async with semaphore:
            if _is_cancelled(batch_id):
                # Cooperative cancellation: we check this before starting each
                # file's work, not mid-OCR-call — Python can't cleanly abort a
                # thread that's already inside a blocking Tesseract call.
                # Anything already running when cancel was clicked finishes;
                # everything still queued stops here. _cancel_batch_row()
                # (called from the /cancel endpoint) has already marked this
                # job 'cancelled' in the DB, so just skip it.
                return

            if rec.is_duplicate:
                _db_execute(db_path, _update_job, job_id, status="duplicate")
                _db_execute(db_path, _bump_batch_counts, batch_id, duplicate_files=1)
                await manager.broadcast(batch_id, {
                    "type": "file_done", "job_id": job_id, "filename": rec.filename,
                    "status": "duplicate",
                })
                return

            _db_execute(db_path, _update_job, job_id, status="extracting")
            await manager.broadcast(batch_id, {
                "type": "file_progress", "job_id": job_id, "filename": rec.filename,
                "status": "extracting",
            })

            try:
                record = await loop.run_in_executor(EXECUTOR, process_one_file, rec, use_tier2)
            except Exception as e:
                _db_execute(db_path, _update_job, job_id, status="failed", error=str(e))
                _db_execute(db_path, _bump_batch_counts, batch_id, failed_files=1)
                await manager.broadcast(batch_id, {
                    "type": "file_done", "job_id": job_id, "filename": rec.filename,
                    "status": "failed", "error": str(e),
                })
                return

            if _is_cancelled(batch_id):
                # Cancelled while this file's OCR/extraction was in flight.
                # Let it finish (we already paid the cost), but don't write
                # it into the catalog — the admin asked us to stop.
                _db_execute(db_path, _update_job, job_id, status="cancelled")
                await manager.broadcast(batch_id, {
                    "type": "file_done", "job_id": job_id, "filename": rec.filename,
                    "status": "cancelled",
                })
                return

            catalog_id = _db_execute(db_path, upsert_record, record)
            final_status = "needs_review" if record["needs_review"] else "done"
            _db_execute(db_path, _update_job, job_id, status=final_status, catalog_id=catalog_id)
            if record["needs_review"]:
                _db_execute(db_path, _bump_batch_counts, batch_id, needs_review_files=1)
            else:
                _db_execute(db_path, _bump_batch_counts, batch_id, processed_files=1)

            await manager.broadcast(batch_id, {
                "type": "file_done", "job_id": job_id, "filename": rec.filename,
                "status": final_status, "catalog_id": catalog_id,
                "subject": record["subject"], "level": record["level"], "year": record["year"],
            })

    await asyncio.gather(*(handle_one(rec) for rec in records))

    if _is_cancelled(batch_id):
        _cancelled_batches.discard(batch_id)
        await manager.broadcast(batch_id, {"type": "batch_cancelled", "batch_id": batch_id})
        return

    _db_execute(db_path, _finish_batch, batch_id)
    await manager.broadcast(batch_id, {"type": "batch_done", "batch_id": batch_id})
