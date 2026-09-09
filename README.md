# ExamVault — Resource Catalog Platform

Built through **Phase 0 (pipeline) + Phase 1 (read-only web app) + a first pass at Phase 2
(multi-admin auth, bulk import as a real background job queue with live progress, review
queue, catalog management)**.

## What's here

```
resource-catalog/
├── pipeline/            # Phase 0 — ingestion pipeline
│   ├── intake.py          # hashing + duplicate detection
│   ├── extraction.py      # digital text extraction + OCR path
│   ├── metadata.py        # tier-1 regex + tier-2 LLM fallback
│   ├── db.py               # SQLite schema (catalog + admin + jobs), with migrations
│   └── run_pipeline.py     # CLI runner; process_one_file() is reused by the job queue
├── backend/             # FastAPI
│   ├── main.py             # public/student API: search, facets, subjects, latest, popular
│   ├── auth.py             # bcrypt + JWT, multi-admin
│   ├── admin_routes.py      # auth endpoints, bulk import, review queue, catalog editing
│   └── jobs.py              # background job queue + WebSocket live progress
├── frontend/            # React (Vite)
│   └── src/
│       ├── styles/tokens.css   # Academic Clarity design tokens (light) + a dark variant
│       ├── styles/app.css       # all component styles
│       ├── pages/student/       # Home, Browse (search/subject/latest/popular), Subjects, PaperDetails
│       └── pages/admin/         # Login, Dashboard, Import (live monitor), ReviewQueue, Catalog
└── data/
    ├── intake/           # drop source folders here for local testing
    └── catalog/           # catalog.db lands here
```

## Auth model

First `/auth/register` call creates the sole bootstrap admin; every subsequent register
attempt is rejected (`403`) until an authenticated admin adds more via `POST /admin/users`.
Tokens are JWT, 12-hour expiry, passed as `Authorization: Bearer <token>` for REST calls and
as a `?token=` query param for the WebSocket (browsers can't set headers on the WS handshake).

**`SETUP_KEY`** — without this, `/auth/register` is open to whoever reaches it first while the
admin table is empty. On a real deployment that's a race: a stranger who finds the URL before
you finish setup becomes the admin. Set `SETUP_KEY` and the bootstrap request must include a
matching `setup_key` field or it's rejected with `403`:
```bash
export SETUP_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
```
Share that value with yourself out-of-band (not over the same channel as the deployment URL)
and paste it into the "Setup key" field the registration form shows. Once the bootstrap admin
exists, `SETUP_KEY` no longer matters — adding further admins via `/admin/users` already
requires being logged in.

**`JWT_SECRET`** — if this environment variable isn't set, the backend generates a random
secret at process start and prints a warning. That's intentionally safer than a fixed
fallback baked into source code (which would make tokens forgeable by anyone who's seen the
code), but it means **every admin session is invalidated on restart** until you set a real
one. Set it to a long random value before deploying anywhere that needs sessions to survive
a restart:
```bash
export JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

**Password requirements**: minimum 8 characters, enforced at the API level on
`/auth/register` and `/admin/users`.

**Brute-force protection**, two independent layers:
- Rate limiting: 5 requests/minute per IP on `/auth/login` and `/auth/register`.
- Account lockout: 5 failed logins for a given *username* (regardless of source IP) locks
  that account for 15 minutes. This is what stops a distributed attack — many IPs targeting
  one account — that IP-based rate limiting alone wouldn't catch. Both are in-memory and
  per-process, same trade-off as the job queue below: fine for one backend instance, resets
  on restart.

**CORS**: `ALLOWED_ORIGINS` env var, comma-separated list of real frontend origins (e.g.
`https://examvault.example.com`). Defaults to local dev ports only if unset — never
wildcard-open by default, since `allow_origins=["*"]` would let any website call this API
from a browser holding a valid token.

**Upload size limit**: 50MB per file on `/admin/import/upload`, returns `413` over that.

## Background job queue

Two ways to start an import:

- **`POST /admin/import/upload`** (multipart file upload) — what the UI's drag-and-drop /
  "Select folder" uses. Files are uploaded through the browser and saved server-side into
  their own `data/intake/uploads/<random-id>/` folder, so this works regardless of whether the
  browser and backend are on the same machine (i.e. it works after deploying, unlike the path
  option below).
- **`POST /admin/import`** (JSON body: `{"source_folder": "..."}`) — points at a folder that
  already exists on the machine the backend process is running on. Only useful for local dev
  or if you're running the backend and your papers on the same box.

Either way, once the files are located, the same pipeline runs: hashes them, creates DB rows
for the batch + one row per file, and returns immediately with a `batch_id`. Processing happens
in an asyncio task using a thread pool for the blocking pipeline work (OCR is CPU-heavy), with
up to 4 files in flight at once. Connect to `wss://.../admin/batches/{id}/live?token=...` for
live per-file status pushes, or poll `GET /admin/batches/{id}` for the same data.

**Cancelling a running batch:** `POST /admin/batches/{id}/cancel`. Cancellation is cooperative
— checked between files, not mid-file — since Python can't cleanly interrupt a thread that's
already inside a blocking Tesseract call. Anything not yet started stops immediately; whatever's
mid-OCR when you cancel finishes that pass but its result is discarded rather than cataloged.

This is genuinely non-blocking and concurrent, but **in-process** — fine for one backend
instance. If you outgrow a single instance (e.g. running multiple backend replicas behind a
load balancer), swap `jobs.py`'s `ThreadPoolExecutor` + `asyncio.create_task` for
Redis + RQ or Celery, broadcasting progress via Redis pub/sub instead of the in-memory
`ConnectionManager`. The DB schema (`import_batches`, `import_jobs`) doesn't need to change.

**Heads up if you deploy the backend to a free tier with spin-down** (e.g. Render free): spin-down
is triggered by idle *HTTP* traffic, not idle CPU, so a long unattended OCR batch can still get
killed mid-run even though it's actively working. Fine for imports you're watching in the UI
(the live-progress polling counts as traffic); for large unattended batches, either run locally
or use an always-on tier.

## OCR sample test result (from an earlier session)

Ran against 2 representative files: a clean digital PDF extracted its text layer directly (no
OCR), and a scanned PDF OCR'd at ~90–94% mean word confidence via Tesseract — confirms Tesseract
is sufficient, no Cloud Vision fallback needed. Run the full 20-file test from the original spec
against your real corpus before a full production import, to confirm this holds across your
actual scan-quality distribution.

## Running everything locally

**Prerequisite — Tesseract OCR engine**

`pytesseract` (in `requirements.txt`) is only a Python wrapper — the actual OCR engine has to
be installed separately as a system binary:

- **Windows**: install via the [UB-Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki)
  (the standard Windows installer, since Tesseract itself doesn't publish official Windows
  binaries). `extraction.py` auto-detects the two default install locations
  (`C:\Program Files\Tesseract-OCR\` and the `(x86)` variant) even if the installer didn't add
  it to PATH. If you installed somewhere else, set
  `pytesseract.pytesseract.tesseract_cmd = r"C:\your\path\tesseract.exe"` near the top of
  `pipeline/extraction.py`.
- **macOS**: `brew install tesseract`
- **Linux**: `sudo apt install tesseract-ocr` (Debian/Ubuntu) or your distro's equivalent

Verify with `tesseract --version` in a fresh terminal before running the pipeline.

**Backend:**
```bash
cd backend
pip install -r requirements.txt --break-system-packages
uvicorn main:app --reload --port 8000
```
First run auto-creates all tables (including the Phase 2 additions) via `get_connection()`'s
idempotent schema script — no separate migration step needed for a fresh clone.

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```
Visit `http://localhost:5173`. First visit to `/admin` prompts you to create the bootstrap
admin account. Override the backend URL with `VITE_API_BASE` if deploying separately.

## Deploying to the cloud

- **Backend**: swap `sqlite3` for Postgres (the SQL is plain enough to port directly). Deploy
  as a container — FastAPI works out of the box on Fly.io, Railway, Render.
- **Frontend**: `npm run build` → static `dist/` → any static host. Set `VITE_API_BASE` at
  build time.
- **File storage**: move actual PDFs to S3-compatible object storage before deploying; update
  `download_paper()` in `main.py` to fetch by object key instead of local path.
- **Job queue at scale**: see the note above — Redis + RQ/Celery once you need multi-instance.
- Set `ALLOWED_ORIGINS` to your real frontend domain (see Auth model above).
- Set `JWT_SECRET` to a stable random value (see Auth model above) — otherwise every deploy/restart logs everyone out.
- Set `SETUP_KEY` before the first deploy (see Auth model above) — otherwise the first person to reach `/auth/register` becomes the admin.
- Set a real `JWT_SECRET` env var.

## What's explicitly not built yet

Public user accounts/uploads (as opposed to admin-side import), near-duplicate detection,
Q&A/community, points/reputation, AI answer-verification — all deliberately deferred per the
original phase plan.

