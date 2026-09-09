"""
Admin-side API: auth, bulk import (kicks off a background job + WebSocket
progress), review queue, catalog editing, and dashboard stats.

Mounted onto the main FastAPI app under /admin and /auth in main.py.
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from auth import (
    hash_password, verify_password, create_access_token, get_current_admin,
    is_locked_out, record_failed_login, clear_failed_logins,
)
from jobs import start_batch, manager, request_cancel, _db_execute, _cancel_batch_row
from rate_limit import limiter

DB_PATH = Path(__file__).parent.parent / "data" / "catalog" / "catalog.db"
UPLOAD_ROOT = Path(__file__).parent.parent / "data" / "intake" / "uploads"
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50MB per file
MAX_BATCH_SIZE_BYTES = 1024 * 1024 * 1024  # 1GB per batch
MAX_FILES_PER_BATCH = 500
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".jpg", ".jpeg", ".png"}

# Gates the one-time bootstrap registration (creating the very first admin
# account). Without this, /auth/register is open to anyone as long as the
# admin table is empty — meaning on a fresh public deployment, whoever hits
# that endpoint first (you, or a stranger who found the URL before you
# finished setup) becomes the admin. Setting SETUP_KEY closes that race:
# only someone who knows this value can complete the bootstrap.
SETUP_KEY = os.environ.get("SETUP_KEY")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
if not SETUP_KEY:
    print(
        "\n[admin_routes] WARNING: SETUP_KEY is not set — the first-admin "
        "bootstrap at /auth/register is open to anyone who reaches it before "
        "you do. Fine for local dev; set SETUP_KEY before deploying "
        "anywhere reachable by the public.\n"
    )

router = APIRouter()


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------- Auth ----------

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=200)
    setup_key: Optional[str] = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class AddAdminRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=10, max_length=200)


class AdminUpdateRequest(BaseModel):
    username: Optional[str] = Field(default=None, min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    is_active: Optional[bool] = None


def _admin_count(conn: sqlite3.Connection, active_only: bool = False) -> int:
    sql = "SELECT COUNT(*) FROM admin_users" + (" WHERE is_active = 1" if active_only else "")
    return int(conn.execute(sql).fetchone()[0])


def _audit_admin(conn: sqlite3.Connection, actor_id: Optional[int], target_id: Optional[int], action: str, details: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO admin_audit_log (admin_id, target_admin_id, action, details) VALUES (?, ?, ?, ?)",
        (actor_id, target_id, action, json.dumps(details or {}, default=str)),
    )


def _public_admin(row: sqlite3.Row | dict) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login_at": row["last_login_at"],
        "password_changed_at": row["password_changed_at"],
    }


@router.get("/auth/setup-status")
def setup_status():
    """Public bootstrap status. Registration is only available while there are no admins."""
    conn = get_db()
    try:
        count = _admin_count(conn)
        return {"setup_required": count == 0, "setup_key_required": bool(SETUP_KEY)}
    finally:
        conn.close()


@router.post("/auth/register", response_model=TokenResponse)
@limiter.limit("5/minute")
def register(request: Request, body: RegisterRequest):
    """Create the first administrator only. Once any admin exists this endpoint is permanently closed."""
    conn = get_db()
    try:
        if _admin_count(conn) > 0:
            raise HTTPException(403, "Initial setup is already complete. Ask an existing admin to add you.")
        if not SETUP_KEY:
            if ENVIRONMENT != "development":
                raise HTTPException(503, "SETUP_KEY must be configured before bootstrap registration is enabled")
        elif not body.setup_key or not secrets.compare_digest(body.setup_key, SETUP_KEY):
            raise HTTPException(403, "Invalid or missing setup key.")

        now = datetime.utcnow().isoformat(timespec="seconds")
        pw_hash = hash_password(body.password)
        cur = conn.execute(
            "INSERT INTO admin_users (username, password_hash, role, is_active, updated_at, password_changed_at) VALUES (?, ?, 'admin', 1, ?, ?)",
            (body.username.strip(), pw_hash, now, now),
        )
        new_id = cur.lastrowid
        assert new_id is not None
        _audit_admin(conn, new_id, new_id, "bootstrap_created", {"username": body.username.strip()})
        conn.commit()
        token = create_access_token(new_id, body.username.strip(), "admin", 1)
        return TokenResponse(access_token=token, username=body.username.strip(), role="admin")
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Username already taken")
    finally:
        conn.close()


@router.post("/auth/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, body: LoginRequest):
    locked, seconds_remaining = is_locked_out(body.username.lower())
    if locked:
        minutes = max(1, seconds_remaining // 60)
        raise HTTPException(429, f"Too many failed attempts for this account. Try again in about {minutes} minute(s).")

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, role, is_active, session_version FROM admin_users WHERE username = ? COLLATE NOCASE",
            (body.username.strip(),),
        ).fetchone()
        if not row or not verify_password(body.password, row["password_hash"]):
            record_failed_login(body.username.lower())
            raise HTTPException(401, "Invalid username or password")
        if not row["is_active"] or row["role"] != "admin":
            raise HTTPException(403, "This administrator account is disabled")
        clear_failed_logins(body.username.lower())
        now = datetime.utcnow().isoformat(timespec="seconds")
        conn.execute("UPDATE admin_users SET last_login_at = ?, updated_at = ? WHERE id = ?", (now, now, row["id"]))
        _audit_admin(conn, row["id"], row["id"], "login")
        conn.commit()
        token = create_access_token(row["id"], row["username"], row["role"], row["session_version"])
        return TokenResponse(access_token=token, username=row["username"], role=row["role"])
    finally:
        conn.close()


@router.get("/admin/me")
def current_admin(current=Depends(get_current_admin)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM admin_users WHERE id = ?", (current["id"],)).fetchone()
        if not row:
            raise HTTPException(401, "Administrator account not found")
        return _public_admin(row)
    finally:
        conn.close()


@router.get("/admin/users")
def list_admins(current=Depends(get_current_admin)):
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM admin_users ORDER BY is_active DESC, username COLLATE NOCASE").fetchall()
        return [_public_admin(r) for r in rows]
    finally:
        conn.close()


@router.post("/admin/users", response_model=dict)
def add_admin(body: AddAdminRequest, current=Depends(get_current_admin)):
    username = body.username.strip()
    conn = get_db()
    try:
        now = datetime.utcnow().isoformat(timespec="seconds")
        pw_hash = hash_password(body.password)
        cur = conn.execute(
            "INSERT INTO admin_users (username, password_hash, role, is_active, updated_at, password_changed_at) VALUES (?, ?, 'admin', 1, ?, ?)",
            (username, pw_hash, now, now),
        )
        new_id = cur.lastrowid
        assert new_id is not None
        _audit_admin(conn, current["id"], new_id, "created", {"username": username})
        conn.commit()
        return _public_admin(conn.execute("SELECT * FROM admin_users WHERE id = ?", (new_id,)).fetchone())
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Username already taken")
    finally:
        conn.close()


@router.post("/admin/me/password")
def change_own_password(body: ChangePasswordRequest, current=Depends(get_current_admin)):
    conn = get_db()
    try:
        row = conn.execute("SELECT password_hash FROM admin_users WHERE id = ? AND is_active = 1", (current["id"],)).fetchone()
        if not row or not verify_password(body.current_password, row["password_hash"]):
            raise HTTPException(400, "Current password is incorrect")
        now = datetime.utcnow().isoformat(timespec="seconds")
        conn.execute("UPDATE admin_users SET password_hash = ?, password_changed_at = ?, updated_at = ?, session_version = session_version + 1 WHERE id = ?", (hash_password(body.new_password), now, now, current["id"]))
        _audit_admin(conn, current["id"], current["id"], "password_changed")
        conn.commit()
        return {"message": "Password changed. Existing sessions remain valid until they expire."}
    finally:
        conn.close()


@router.patch("/admin/users/{admin_id}")
def update_admin(admin_id: int, body: AdminUpdateRequest, current=Depends(get_current_admin)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM admin_users WHERE id = ?", (admin_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Administrator not found")
        if body.username is None and body.is_active is None:
            raise HTTPException(400, "No changes supplied")
        if admin_id == current["id"] and body.is_active is False:
            raise HTTPException(400, "You cannot disable your own account")
        if body.is_active is False and row["is_active"] and _admin_count(conn, active_only=True) <= 1:
            raise HTTPException(400, "The last active administrator cannot be disabled")

        fields, params, changes = [], [], {}
        if body.username is not None:
            username = body.username.strip()
            if username.lower() != row["username"].lower():
                fields.append("username = ?"); params.append(username); changes["username"] = {"from": row["username"], "to": username}
        if body.is_active is not None and bool(body.is_active) != bool(row["is_active"]):
            fields.append("is_active = ?"); params.append(1 if body.is_active else 0); changes["is_active"] = {"from": bool(row["is_active"]), "to": bool(body.is_active)}
        if not fields:
            return _public_admin(row)
        now = datetime.utcnow().isoformat(timespec="seconds")
        fields.append("updated_at = ?"); params.append(now); params.append(admin_id)
        try:
            conn.execute(f"UPDATE admin_users SET {', '.join(fields)} WHERE id = ?", params)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Username already taken")
        _audit_admin(conn, current["id"], admin_id, "updated", changes)
        conn.commit()
        return _public_admin(conn.execute("SELECT * FROM admin_users WHERE id = ?", (admin_id,)).fetchone())
    finally:
        conn.close()


@router.post("/admin/users/{admin_id}/reset-password")
def reset_admin_password(admin_id: int, body: ResetPasswordRequest, current=Depends(get_current_admin)):
    conn = get_db()
    try:
        row = conn.execute("SELECT id, username FROM admin_users WHERE id = ?", (admin_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Administrator not found")
        now = datetime.utcnow().isoformat(timespec="seconds")
        conn.execute("UPDATE admin_users SET password_hash = ?, password_changed_at = ?, updated_at = ?, session_version = session_version + 1 WHERE id = ?", (hash_password(body.password), now, now, admin_id))
        _audit_admin(conn, current["id"], admin_id, "password_reset")
        conn.commit()
        return {"message": "Password reset successfully. Existing sessions for this account have been revoked."}
    finally:
        conn.close()


@router.get("/admin/users/audit")
def admin_audit(limit: int = 100, current=Depends(get_current_admin)):
    limit = max(1, min(limit, 200))
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT a.id, a.action, a.details, a.created_at,
                      actor.username AS actor_username, target.username AS target_username
               FROM admin_audit_log a
               LEFT JOIN admin_users actor ON actor.id = a.admin_id
               LEFT JOIN admin_users target ON target.id = a.target_admin_id
               ORDER BY a.id DESC LIMIT ?""", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.delete("/admin/users/{admin_id}")
def delete_admin(admin_id: int, current=Depends(get_current_admin)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM admin_users WHERE id = ?", (admin_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Administrator not found")
        if admin_id == current["id"]:
            raise HTTPException(400, "You cannot delete your own account")
        if row["is_active"] and _admin_count(conn, active_only=True) <= 1:
            raise HTTPException(400, "The last active administrator cannot be deleted")
        _audit_admin(conn, current["id"], admin_id, "deleted", {"username": row["username"]})
        conn.execute("UPDATE import_batches SET created_by = NULL WHERE created_by = ?", (admin_id,))
        conn.execute("DELETE FROM admin_users WHERE id = ?", (admin_id,))
        conn.commit()
        return {"message": "Administrator deleted"}
    finally:
        conn.close()


# ---------- Bulk import ----------

class ImportRequest(BaseModel):
    source_folder: str
    use_tier2: bool = True


@router.post("/admin/import")
async def import_folder(body: ImportRequest, current=Depends(get_current_admin)):
    """
    Path-based import: the folder must exist on the machine the backend
    process is running on. Handy for local dev, but doesn't work once the
    browser and the backend are on different machines (e.g. after deploying)
    — for that, use /admin/import/upload below, which the UI's drag-and-drop
    / folder-select uses.
    """
    if not Path(body.source_folder).exists():
        raise HTTPException(400, f"Folder not found: {body.source_folder}")
    batch_id = await start_batch(str(DB_PATH), body.source_folder, current["id"], body.use_tier2)
    return {"batch_id": batch_id, "status": "running"}


@router.post("/admin/import/upload")
async def import_upload(
    files: list[UploadFile] = File(...),
    use_tier2: bool = Form(True),
    current=Depends(get_current_admin),
):
    """
    Accepts files uploaded directly from the browser (drag-and-drop or a
    folder picker) instead of a server-side path. Each import gets its own
    subfolder under data/intake/uploads/ so batches never collide, and
    filename clashes within one batch get a short random prefix rather than
    silently overwriting each other.

    Uses the same start_batch() as the path-based import — once the files
    are on disk, it's the identical pipeline either way.
    """
    if not files:
        raise HTTPException(400, "No files were uploaded")
    if len(files) > MAX_FILES_PER_BATCH:
        raise HTTPException(413, f"A batch may contain at most {MAX_FILES_PER_BATCH} files")

    batch_dir = UPLOAD_ROOT / f"{uuid.uuid4().hex[:12]}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    seen_names: set[str] = set()
    total_bytes = 0
    try:
        for f in files:
            name = Path(f.filename or "unnamed").name
            ext = Path(name).suffix.lower()
            if ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(415, f"'{name}' has an unsupported file type")
            if name in seen_names:
                name = f"{uuid.uuid4().hex[:6]}_{name}"
            seen_names.add(name)

            dest = batch_dir / name
            size = 0
            with dest.open("wb") as out:
                while True:
                    chunk = await f.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    total_bytes += len(chunk)
                    if size > MAX_UPLOAD_SIZE_BYTES:
                        raise HTTPException(413, f"'{name}' is over the 50MB per-file limit")
                    if total_bytes > MAX_BATCH_SIZE_BYTES:
                        raise HTTPException(413, "Batch exceeds the 1GB total upload limit")
                    out.write(chunk)

            head = dest.read_bytes()[:16]
            valid = ((ext == ".pdf" and head.startswith(b"%PDF-")) or
                     (ext == ".png" and head.startswith(b"\x89PNG\r\n\x1a\n")) or
                     (ext in {".jpg", ".jpeg"} and head.startswith(b"\xff\xd8\xff")) or
                     (ext == ".docx" and head.startswith(b"PK\x03\x04")))
            if not valid:
                raise HTTPException(415, f"'{name}' content does not match its extension")
    except Exception:
        for written in batch_dir.iterdir():
            written.unlink(missing_ok=True)
        batch_dir.rmdir()
        raise

    batch_id = await start_batch(str(DB_PATH), str(batch_dir), current["id"], use_tier2)
    return {"batch_id": batch_id, "status": "running", "files_received": len(files)}


@router.get("/admin/batches/{batch_id}")
def get_batch(batch_id: int, current=Depends(get_current_admin)):
    conn = get_db()
    try:
        batch = conn.execute("SELECT * FROM import_batches WHERE id = ?", (batch_id,)).fetchone()
        if not batch:
            raise HTTPException(404, "Batch not found")
        jobs = conn.execute(
            "SELECT id, filename, status, catalog_id, error FROM import_jobs "
            "WHERE batch_id = ? ORDER BY id", (batch_id,)
        ).fetchall()
        return {"batch": dict(batch), "jobs": [dict(j) for j in jobs]}
    finally:
        conn.close()


@router.get("/admin/batches")
def list_batches(current=Depends(get_current_admin)):
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM import_batches ORDER BY id DESC LIMIT 25").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/admin/batches/{batch_id}/cancel")
def cancel_batch(batch_id: int, current=Depends(get_current_admin)):
    """
    Stops a running import. Any file already mid-OCR when this is called
    finishes that OCR pass (can't cleanly interrupt a blocking Tesseract call
    from another thread) but its result is discarded rather than cataloged.
    Everything not yet started is marked cancelled immediately.
    """
    conn = get_db()
    try:
        batch = conn.execute("SELECT status FROM import_batches WHERE id = ?", (batch_id,)).fetchone()
        if not batch:
            raise HTTPException(404, "Batch not found")
        if batch["status"] != "running":
            raise HTTPException(400, f"Batch is '{batch['status']}', not running — nothing to cancel")
    finally:
        conn.close()

    request_cancel(batch_id)
    _db_execute(str(DB_PATH), _cancel_batch_row, batch_id)
    return {"batch_id": batch_id, "status": "cancelling"}


@router.websocket("/admin/batches/{batch_id}/live")
async def batch_live(websocket: WebSocket, batch_id: int):
    # Token passed as a query param since browsers can't set headers on WS handshakes.
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return
    from auth import decode_token
    try:
        payload = decode_token(token)
        if payload.get("role") != "admin":
            raise HTTPException(403, "Administrator access required")
        user_id = int(payload["sub"])
        conn = get_db()
        try:
            batch = conn.execute("SELECT created_by FROM import_batches WHERE id = ?", (batch_id,)).fetchone()
        finally:
            conn.close()
        if not batch or batch["created_by"] != user_id:
            await websocket.close(code=4403)
            return
    except (HTTPException, ValueError, KeyError):
        await websocket.close(code=4401)
        return

    await manager.connect(batch_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive; client doesn't need to send anything meaningful
    except WebSocketDisconnect:
        manager.disconnect(batch_id, websocket)


# ---------- Review queue ----------

@router.get("/admin/review-queue")
def review_queue(current=Depends(get_current_admin)):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM catalog WHERE needs_review = 1 ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


class ReviewUpdateRequest(BaseModel):
    subject: Optional[str] = None
    level: Optional[str] = None
    year: Optional[int] = None
    exam_board: Optional[str] = None
    paper_number: Optional[int] = None
    session: Optional[str] = None
    doc_type: Optional[str] = None
    approve: bool = True


@router.patch("/admin/catalog/{catalog_id}")
def update_catalog_entry(catalog_id: int, body: ReviewUpdateRequest, current=Depends(get_current_admin)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM catalog WHERE id = ?", (catalog_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Not found")

        if body.session is not None and body.session not in {"June", "November"}:
            raise HTTPException(422, "session must be June or November")
        if body.year is not None and not 2000 <= body.year <= datetime.now().year:
            raise HTTPException(422, f"year must be between 2000 and {datetime.now().year}")
        if body.paper_number is not None and not 1 <= body.paper_number <= 4:
            raise HTTPException(422, "paper_number must be between 1 and 4")
        if body.level is not None and body.level not in {"A-Level", "O-Level", "Form 4", "Form 6"}:
            raise HTTPException(422, "invalid level")
        fields = {k: v for k, v in body.dict(exclude={"approve"}).items() if v is not None}
        fields["needs_review"] = 0 if body.approve else 1
        fields["confidence"] = "manual" if body.approve else "needs_review"

        # syllabus_era is derived from year, not an independent field — if the
        # admin corrects the year, keep the era tag consistent with it rather
        # than leaving a stale value from whatever the pipeline guessed.
        if "year" in fields:
            fields["syllabus_era"] = "pre-2017" if fields["year"] < 2017 else "post-2017"
        if body.approve:
            required = ("subject", "level", "year", "session", "exam_board", "paper_number")
            missing = [f for f in required if fields.get(f, row[f]) in (None, "")]
            if missing:
                raise HTTPException(422, f"Cannot approve: missing {', '.join(missing)}")

        sets = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE catalog SET {sets} WHERE id = ?", (*fields.values(), catalog_id))
        changes = {}
        for key, value in fields.items():
            if key in row.keys() and row[key] != value:
                changes[key] = {"from": row[key], "to": value}
        conn.execute(
            "INSERT INTO catalog_audit_log (catalog_id, admin_id, action, changes) VALUES (?, ?, ?, ?)",
            (catalog_id, current["id"], "approve" if body.approve else "edit", json.dumps(changes, default=str)),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM catalog WHERE id = ?", (catalog_id,)).fetchone())
    finally:
        conn.close()


# ---------- Dashboard ----------

@router.get("/admin/dashboard")
def dashboard(current=Depends(get_current_admin)):
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM catalog").fetchone()[0]
        needs_review = conn.execute("SELECT COUNT(*) FROM catalog WHERE needs_review = 1").fetchone()[0]
        recent_batches = conn.execute(
            "SELECT * FROM import_batches ORDER BY id DESC LIMIT 5"
        ).fetchall()
        by_subject = conn.execute(
            "SELECT subject, COUNT(*) as n FROM catalog WHERE subject IS NOT NULL "
            "GROUP BY subject ORDER BY n DESC"
        ).fetchall()
        return {
            "total_catalog_entries": total,
            "needs_review": needs_review,
            "recent_batches": [dict(b) for b in recent_batches],
            "by_subject": [dict(r) for r in by_subject],
        }
    finally:
        conn.close()
