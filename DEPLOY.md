# Cheapest deployment

Recommended student/prototype setup:

- Frontend: Cloudflare Pages (free static hosting)
- API: Render free web service (FastAPI)
- PostgreSQL: Supabase free tier
- PDFs: Cloudflare R2 object storage
- OCR: run the ingestion pipeline locally on the laptop rather than paying for a worker

Do not use the current local SQLite database or local upload directory as production persistent storage on Render. Its filesystem is ephemeral. Migrate catalog metadata to PostgreSQL and uploaded documents to R2 before relying on cloud persistence.

For local development, SQLite and `data/intake/uploads` remain supported.

Production environment variables: `JWT_SECRET`, `SETUP_KEY`, `ENVIRONMENT=production`, `ALLOWED_ORIGINS`, and optionally `ANTHROPIC_API_KEY`.
