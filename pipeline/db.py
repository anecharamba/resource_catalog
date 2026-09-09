"""
Stage 2.6 — Output

SQLite for local/dev use. Schema is deliberately plain SQL (no ORM-specific
quirks) so porting to Postgres for cloud deployment later is a straight
`CREATE TABLE` copy — see backend/DEPLOY.md for the Postgres migration note.
"""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE,
    subject TEXT,
    level TEXT,
    year INTEGER,
    syllabus_era TEXT,
    session TEXT,           -- 'June' | 'November' | NULL (the exam sitting, distinct from year)
    paper_number INTEGER,
    doc_type TEXT,
    exam_board TEXT,
    extraction_method TEXT,
    confidence TEXT,          -- 'auto' | 'needs_review'
    needs_review BOOLEAN DEFAULT 0,
    review_reasons TEXT,
    text_snippet TEXT,        -- first ~500 chars, for the manual-review glance
    download_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_catalog_subject ON catalog(subject);
CREATE INDEX IF NOT EXISTS idx_catalog_level ON catalog(level);
CREATE INDEX IF NOT EXISTS idx_catalog_year ON catalog(year);
CREATE INDEX IF NOT EXISTS idx_catalog_needs_review ON catalog(needs_review);

CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin',
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_login_at TEXT,
    password_changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    session_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_folder TEXT NOT NULL,
    created_by INTEGER REFERENCES admin_users(id),
    status TEXT NOT NULL DEFAULT 'queued',  -- queued | running | done | cancelled | failed
    total_files INTEGER DEFAULT 0,
    processed_files INTEGER DEFAULT 0,
    duplicate_files INTEGER DEFAULT 0,
    needs_review_files INTEGER DEFAULT 0,
    failed_files INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS import_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id),
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    -- queued | extracting | done | duplicate | needs_review | failed | cancelled
    catalog_id INTEGER,
    error TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_batch ON import_jobs(batch_id);

CREATE TABLE IF NOT EXISTS admin_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER REFERENCES admin_users(id),
    target_admin_id INTEGER REFERENCES admin_users(id),
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_admin_audit_target ON admin_audit_log(target_admin_id);

CREATE TABLE IF NOT EXISTS catalog_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_id INTEGER NOT NULL REFERENCES catalog(id),
    admin_id INTEGER NOT NULL REFERENCES admin_users(id),
    action TEXT NOT NULL,
    changes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_catalog ON catalog_audit_log(catalog_id);
"""


def get_connection(db_path: str = "data/catalog/catalog.db") -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Adds columns introduced after initial release to any pre-existing DB file."""
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(catalog)").fetchall()}
    if "session" not in existing_cols:
        conn.execute("ALTER TABLE catalog ADD COLUMN session TEXT")
        conn.commit()
    if "download_count" not in existing_cols:
        conn.execute("ALTER TABLE catalog ADD COLUMN download_count INTEGER DEFAULT 0")
        conn.commit()

    admin_cols = {row[1] for row in conn.execute("PRAGMA table_info(admin_users)").fetchall()}
    if "is_active" not in admin_cols:
        conn.execute("ALTER TABLE admin_users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
    if "updated_at" not in admin_cols:
        conn.execute("ALTER TABLE admin_users ADD COLUMN updated_at TEXT")
    if "last_login_at" not in admin_cols:
        conn.execute("ALTER TABLE admin_users ADD COLUMN last_login_at TEXT")
    if "password_changed_at" not in admin_cols:
        conn.execute("ALTER TABLE admin_users ADD COLUMN password_changed_at TEXT")
    if "session_version" not in admin_cols:
        conn.execute("ALTER TABLE admin_users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 1")
    conn.execute("UPDATE admin_users SET is_active = 1 WHERE is_active IS NULL")
    conn.execute("UPDATE admin_users SET session_version = 1 WHERE session_version IS NULL")
    conn.execute("UPDATE admin_users SET password_changed_at = COALESCE(password_changed_at, created_at)")
    conn.commit()


def upsert_record(conn: sqlite3.Connection, record: dict) -> int:
    cols = [
        "filename", "path", "hash", "subject", "level", "year", "syllabus_era",
        "session", "paper_number", "doc_type", "exam_board", "extraction_method",
        "confidence", "needs_review", "review_reasons", "text_snippet",
    ]
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    update_clause = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "hash")

    sql = f"""
        INSERT INTO catalog ({col_list})
        VALUES ({placeholders})
        ON CONFLICT(hash) DO UPDATE SET {update_clause}
    """
    values = [record.get(c) for c in cols]
    cur = conn.execute(sql, values)
    conn.commit()

    # lastrowid is only reliably set on the fresh-INSERT path; on the
    # ON CONFLICT...DO UPDATE path (re-processing a file whose hash already
    # exists) it isn't guaranteed, so fall back to looking the row up by its
    # unique hash.
    if cur.lastrowid is not None:
        return cur.lastrowid

    row = conn.execute("SELECT id FROM catalog WHERE hash = ?", (record["hash"],)).fetchone()
    return row["id"]
